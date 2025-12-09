"""
TODO: make this functional
Job manager that manages jobs and keeps track of their status.
Ideally works for both local and remote runs.
"""
import json
import os
from multiprocessing import Manager, Process
import socket
import threading
from time import sleep
import time
from typing import List

from stnd.run_with_monitor.job import Job, find_job_idx
from stnd.run_with_monitor.utility.utils import make_run_with_monitor_updates_dir


def get_my_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(("10.254.254.254", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        s.close()
    return IP


class JobManager:
    def __init__(self, local_run, open_socket, logger, use_files=False, file_updates_dir=None):
        self.local_run = local_run
        self.logger = logger

        self.server_ip = None
        self.server_port = None

        self.manager = Manager()
        self.manager_lock = self.manager.Lock()

        self.jobs: List[Job] = self.manager.list()  # Shared list
        self.open_socket = open_socket
        self.use_files = use_files
        self.file_updates_dir = None
        self._file_positions = {}

        if open_socket:
            self.server_info = self.manager.dict()  # Shared dictionary
            self.queue = self.manager.Queue()  # Shared queue
            self.server_process = Process(target=self.run_server)
            self.server_process.start()

            # Wait until server IP and port are set
            # while 'ip' not in self.server_info or 'port' not in self.server_info:
            #     sleep(1)

            while True:
                with self.manager_lock:
                    if "ip" in self.server_info and "port" in self.server_info:
                        break
                sleep(1)
            self.server_ip = self.server_info["ip"]
            self.server_port = self.server_info["port"]
        elif self.use_files:
            if file_updates_dir is None:
                self.file_updates_dir = make_run_with_monitor_updates_dir()
            else:
                self.file_updates_dir = file_updates_dir
                os.makedirs(self.file_updates_dir, exist_ok=True)

    def _recv_exact(self, client: socket.socket, expected_len: int, label="") -> bytes:
        """
        Receive exactly expected_len bytes from the socket.
        Returns None if the connection closes before all bytes arrive.
        """
        if expected_len <= 0:
            return b""

        data = bytearray()
        while len(data) < expected_len:
            try:
                chunk = client.recv(min(4096, expected_len - len(data)))
                if chunk:
                    print(
                        f"DEBUG: recv_exact{f' ({label})' if label else ''} "
                        f"read {len(chunk)} bytes (have {len(data) + len(chunk)}/{expected_len})",
                        flush=True,
                    )
            except socket.timeout:
                # Client is still connected but has not sent more data yet.
                # Keep waiting instead of tearing down the connection.
                print(
                    f"DEBUG: recv_exact timeout{f' ({label})' if label else ''} "
                    f"- still waiting {expected_len - len(data)} bytes",
                    flush=True,
                )
                continue

            if not chunk:
                return None

            data.extend(chunk)

        return bytes(data)

    def process_job_message(self, message):
        """
        Process a message from a job.

        args:
            message (dict): message from a job in JSON format.

        """
        assert "job_id" in message, "Job ID not found in message"
        job_id = message["job_id"]

        with self.manager_lock:
            job_idx = find_job_idx(self.jobs, job_id)
            if job_idx is not None:
                job = self.jobs[job_idx]
            else:
                self.logger.log(f"Job {job_id} not found -- creating a new job")

                # Should we create a new job?
                job = Job(job_id, None, None, None)
                self.jobs.append(job)
                job_idx = len(self.jobs) - 1

            # Unsure if this will update the job in the list
            job.process_message(message)

            self.jobs[job_idx] = job

    def handle_client(self, client: socket.socket, queue, addr=None):
        print(
            f"DEBUG: New client connection handler started from {addr if addr else 'unknown'}",
            flush=True,
        )
        client.settimeout(15.0) # Timeout if client is silent
        with client:
            while True:
                try:
                    # Read the first 4 bytes to get the message length
                    print("DEBUG: Waiting for length header...", flush=True)
                    length_data = self._recv_exact(client, 4, label="header")
                    if not length_data:
                        print("DEBUG: No length data received (client closed?)", flush=True)
                        break

                    message_length = int.from_bytes(length_data, "big")
                    print(f"DEBUG: Header received. Expecting {message_length} bytes.", flush=True)

                    # Read the actual message: Read in chunks until we have full message
                    print(f"DEBUG: Waiting for {message_length} bytes of body...", flush=True)

                    data = self._recv_exact(client, message_length, label="body")
                    received_len = len(data) if data else 0
                    print(f"DEBUG: Body received. Got {received_len} bytes.", flush=True)

                    if data is None:
                        print(
                            f"Warning: Incomplete message. Expected {message_length}, got {received_len}",
                            flush=True,
                        )
                        break
                    if len(data) < message_length:
                        print(
                            f"Warning: Incomplete message. Expected {message_length}, got {received_len}",
                            flush=True,
                        )
                        break

                    # Deserialize the message
                    try:
                        message_obj = json.loads(data.decode("utf-8"))
                        print("DEBUG: JSON deserialized successfully", flush=True)
                    except:
                        print("Warning: Failed to deserialize message", flush=True)
                        try:
                             print(
                                f"Tried to deserialize: {data}\n which decoded to {data.decode('utf-8')}", flush=True
                            )
                        except:
                             pass
                        break
                    
                    assert "job_id" in message_obj, "Job ID not found in message"
                    assert "messages" in message_obj, "Messages not found in message"

                    # Might need to update or add a new job
                    self.process_job_message(message_obj)

                    # print(f"Received a message from {message_obj['job_id']}", flush=True)
                    queue.put(message_obj)
                    client.sendall(b"ACK")
                    print("DEBUG: ACK sent", flush=True)
                except Exception as e:
                    print(f"Error handling client: {e}", flush=True)
                    break

                time.sleep(0.01)  # Sleep for 10 milliseconds

    def run_server(self):
        HOST = get_my_ip()  # Assuming you have this function from the previous example
        # Allow stable port via env; otherwise pick a free one so multiple monitors can coexist
        PORT_ENV = os.environ.get("STND_SOCKET_PORT")
        PORT = int(PORT_ENV) if PORT_ENV is not None else 0

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, PORT))
            s.listen()
            actual_port = s.getsockname()[1]  # Get the port chosen by the OS

            with self.manager_lock:
                self.server_info["ip"] = HOST
                self.server_info["port"] = actual_port

            self.logger.log(f"Server listening on {HOST}:{actual_port}")
            if PORT_ENV is None:
                self.logger.log("No STND_SOCKET_PORT set; using an OS-assigned free port so multiple monitors can run.")
            else:
                self.logger.log(f"Using fixed port from STND_SOCKET_PORT={PORT}")

            while True:
                client, addr = s.accept()
                # self.logger.log('Connected by', addr)
                # Using threading here to handle multiple clients in the same process
                threading.Thread(target=self.handle_client, args=(client, self.queue, addr)).start()

    def process_messages(self):
        while True:
            if not self.queue.empty():
                message = self.queue.get()
                # Process the message here
                self.logger.log(f"Processing: {message}")

    def poll_file_messages(self):
        if not self.use_files or not self.file_updates_dir:
            return

        try:
            entries = list(os.scandir(self.file_updates_dir))
        except FileNotFoundError:
            return

        for entry in entries:
            if not entry.is_file() or not entry.name.endswith(".jsonl"):
                continue

            path = entry.path
            last_pos = self._file_positions.get(path, 0)
            new_messages = 0
            try:
                with open(path, "r", encoding="utf-8") as fp:
                    fp.seek(last_pos)
                    while True:
                        line = fp.readline()
                        if not line:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            message_obj = json.loads(line)
                        except Exception as exc:
                            print(
                                f"Warning: Failed to parse file message from {path}: {exc}",
                                flush=True,
                            )
                            continue
                        self.process_job_message(message_obj)
                        new_messages += 1
                    self._file_positions[path] = fp.tell()
            except FileNotFoundError:
                self._file_positions.pop(path, None)
                continue
            if new_messages:
                self.logger.log(
                    f"File monitor: processed {new_messages} message(s) from {os.path.basename(path)}"
                )

    def stop_server(self):
        if self.server_process:
            self.server_process.terminate()

    @property
    def get_running_jobs_count(self):
        pass

    @property
    def get_finished_jobs_count(self):
        pass

    @property
    def get_failed_jobs_count(self):
        pass
