import json
import os
import select
import socket
import time
import threading


class MessageType:
    JOB_STARTED = 0
    JOB_ERROR = 1
    JOB_RESULT_UPDATE = 2
    JOB_FINISHED = 3


class MessageClient:
    def __init__(self, server_ip, server_port, logger):
        self.server_ip = server_ip
        self.server_port = server_port
        self.logger = logger
        self.socket = None
        self.connect()

        self.message_queue = []

        self.job_id = self.get_job_name()

        # store for backup - if we can't connect with the server, we can still save the results locally
        # later, we can sync the results with the server
        self.local_csv_info = {}
        self.could_connect = True

    def connect(self, force_reconnect=False):
        self.logger.log(f"Attempting to connect to the server... force_reconnect={force_reconnect}")

        if self.socket and not force_reconnect:
            self.logger.log("Already connected.")
            self.could_connect = True
            return

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_ip, self.server_port))
            self.logger.log("Connection established successfully.")
        except Exception as e:
            self.logger.log(f"Error trying to open the socket: {e}")
            self.socket = None
            self.could_connect = False
            return
        if self.socket is not None:
            self.could_connect = True

    def get_job_name(self):
        return int(os.environ.get("SLURM_JOB_ID", str(os.getpid())))

    def send_start_command(self):
        # job name is either SLURM job id or "local" PID
        self.send_message(MessageType.JOB_STARTED, None, None, sync=True)

    def send_key_val(self, key, val, sync=False):
        self.send_message(MessageType.JOB_RESULT_UPDATE, key, val, sync=sync)

    def sync_with_remote(self):
        if not self.socket:
            self.connect()
        if not self.socket:
            self.logger.log("Socket connection unavailable; keeping logs queued for retry.")
            self.could_connect = False
            return
        if len(self.message_queue) == 0:
            return

        retries = 10
        retry_delay = 2

        message_str = ""

        if self.could_connect:
            for _ in range(retries):
                try:
                    all_messages = []
                    for message_type, message_key, message_value in self.message_queue:
                        # Serialize the message as JSON
                        message_data = {
                            "type": message_type,
                            "key": str(message_key),
                            "value": str(message_value),
                        }
                        all_messages.append(message_data)

                    message_str = json.dumps(
                        {"job_id": self.job_id, "messages": all_messages}
                    ).encode("utf-8")

                    # Send the length of the message first
                    # Send the length of the message first
                    if not self.socket:
                        raise ConnectionError("Socket disconnected before sending.")
                    message_length = len(message_str)
                    self.logger.log(
                        f"DEBUG: sending packet len={message_length} to {self.server_ip}:{self.server_port}, job_id={self.job_id}"
                    )
                    packet = message_length.to_bytes(4, "big") + message_str
                    # Ensure we block during send so data fully leaves before next timeout logic
                    self.socket.settimeout(None)
                    self.socket.sendall(packet)

                    # Wait for ACK with a bounded timeout
                    self.socket.settimeout(10)
                    data = self.socket.recv(1024)
                    if data == b"ACK":
                        self.logger.log("Messages sent successfully!")
                        self.message_queue = []  # Clear the queue after successful send
                        return
                    else:
                        self.logger.log("No ACK received. Retrying...")
                    # self.socket.setblocking(0)  # Set socket to non-blocking
                    #
                    # # Wait for socket to be ready for sending data
                    # ready_to_send = select.select([self.socket], [], [], 10)
                    # if ready_to_send[0]:
                    #     self.socket.sendall(message_length.to_bytes(4, "big"))
                    #     self.socket.sendall(message_str)
                    # else:
                    #     self.logger.log("Timeout occurred while sending data.")
                    #     return

                    # Wait for socket to be ready for receiving data
                    ready_to_receive = select.select([self.socket], [], [], 10)
                    if ready_to_receive[0]:
                        data = self.socket.recv(1024)
                        self.logger.log(f"DEBUG: received raw ACK bytes {data!r}")
                        if data == b"ACK":
                            self.logger.log("Messages sent successfully!")
                            self.message_queue = []  # Clear the queue after successful send
                            return
                        else:
                            self.logger.log("No ACK received. Retrying...")
                    else:
                        self.logger.log("Timeout occurred while waiting for ACK, forcing reconnect.")
                        self.connect(force_reconnect=True)
                        continue
                    # message_length = len(message_str)
                    # self.socket.sendall(message_length.to_bytes(4, "big"))
                    #
                    # # Send the actual message
                    # self.socket.sendall(message_str)
                    #
                    # data = self.socket.recv(1024)
                    # if data == b"ACK":
                    #     self.logger.log("Messages sent successfully!")2
                    #     self.message_queue = []  # Clear the queue after successful send
                    #     return
                    # else:
                    #     self.logger.log("No ACK received. Retrying...")
                except Exception as e:
                    self.logger.log(f"Error: {e}. Retrying in {retry_delay} seconds...")
                    self.logger.log(f"Attempted to log: \n {message_str}")
                    print(f"Error: {e}. Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    # logger.log("Reconnecting...")
                    self.connect(force_reconnect=True)  # Try to reconnect
                    if not self.socket:
                        self.could_connect = False

        self.logger.log("Failed to send messages after multiple retries.")

    def send_message(self, message_type, message_key, message_value, sync=False):
        # add to local thingie if message_type is JOB_RESULT_UPDATE
        if message_type == MessageType.JOB_RESULT_UPDATE:
            self.local_csv_info[message_key] = message_value
        self.message_queue.append((message_type, message_key, message_value))
        if sync:
            self.sync_with_remote()


class FileMessageClient:
    """
    Drop-in replacement for MessageClient that writes messages to per-job files.
    Each message is appended as a JSON line so the monitor can tail the file.
    """

    def __init__(self, updates_dir, logger, auto_flush=True):
        if updates_dir is None:
            raise ValueError("FileMessageClient requires a writable updates directory.")
        self.updates_dir = updates_dir
        self.logger = logger
        self.job_id = self.get_job_name()
        self.message_queue = []
        self.local_csv_info = {}
        self.could_connect = True
        self.auto_flush = auto_flush
        os.makedirs(self.updates_dir, exist_ok=True)
        self.file_path = os.path.join(self.updates_dir, f"{self.job_id}.jsonl")
        self._lock = threading.Lock()

    def connect(self, force_reconnect=False):
        # Provided for API compatibility; nothing to do for file-based logging.
        return True

    def get_job_name(self):
        return int(os.environ.get("SLURM_JOB_ID", str(os.getpid())))

    def send_start_command(self):
        self.send_message(MessageType.JOB_STARTED, None, None, sync=True)

    def send_key_val(self, key, val, sync=False):
        self.send_message(MessageType.JOB_RESULT_UPDATE, key, val, sync=sync)

    def send_message(self, message_type, message_key, message_value, sync=False):
        if message_type == MessageType.JOB_RESULT_UPDATE:
            self.local_csv_info[message_key] = message_value
        self.message_queue.append((message_type, message_key, message_value))
        if sync or self.auto_flush:
            self.sync_with_remote()

    def sync_with_remote(self):
        if len(self.message_queue) == 0:
            return

        all_messages = []
        for message_type, message_key, message_value in self.message_queue:
            message_data = {
                "type": message_type,
                "key": str(message_key),
                "value": str(message_value),
            }
            all_messages.append(message_data)

        message_str = json.dumps({"job_id": self.job_id, "messages": all_messages})

        try:
            os.makedirs(self.updates_dir, exist_ok=True)
            with self._lock:
                with open(self.file_path, "a", encoding="utf-8") as fp:
                    fp.write(message_str + "\n")
                    fp.flush()
                    try:
                        os.fsync(fp.fileno())
                    except OSError:
                        pass
            self.message_queue = []
            self.could_connect = True
        except Exception as e:
            self.logger.log(f"Error writing status file: {e}")
            self.logger.log(f"Attempted to log: \n {message_str}")
            self.could_connect = False
