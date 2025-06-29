import os
import shutil
import sys
import traceback
import wandb
import contextlib
import time
import subprocess
import copy
import gspread
import pandas as pd
import csv
import re
import warnings
from pydrive2.auth import GoogleAuth, RefreshError
from pydrive2.drive import GoogleDrive
import psutil
import multiprocessing as mp
from tempfile import NamedTemporaryFile


# local modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from stnd.utility.utils import (
    QUOTE_CHAR,
    SYSTEM_PLATFORM,
    NULL_CONTEXT,
    get_current_time,
    get_current_run_folder,
    extract_profiler_results,
    write_into_csv_with_column_names,
    touch_file,
    read_json,
    retrier_factory,
    get_value_from_config,
    read_csv_as_dict,
    is_number,
    make_file_lock,
    get_hostname,
    get_system_root_path,
    raise_unknown,
    as_str_for_csv,
    remove_file_or_folder,
    log_or_print,
    get_project_root_path,
    itself_and_lower_upper_case,
    get_with_assert,
)

sys.path.pop(0)


# Condor
CONDOR_PREFIX = "condor"
CONDOR_BID_KEY = "bid"
ENV_VAR_PREFIX = "env_var"


PROGRESS_FREQUENCY = 0.01
INDENT = "    "
LOGGER_ARG_NAME = "logger"


# string style
CONTROL_PREFIX = "\033["
CONTROL_SUFFIX = "m"
CONTROL_SEPARATOR = ";"
DEFAULT_TEXT_STYLE = "0"
BOLD_TEXT_STYLE = "1"
BLACK_COLOR_CODE = "40"
RED_COLOR_CODE = "31"
GREEN_COLOR_CODE = "32"
BLUE_COLOR_CODE = "34"
PURPLE_COLOR_CODE = "35"
CYAN_COLOR_CODE = "36"
WHITE_COLOR_CODE = "37"


# tmp folder name
DEFAULT_EXPERIMENT = "unknown_experiment"
DEFAULT_NAME_PREFIX = "_"


# logger messages
LOG_PREFIX = "(log)"
INFO_PREFIX = "(info)"
ERROR_PREFIX = "(error)"
MAX_LINE_LENGTH = 80
SEPARATOR = "".join(["="] * MAX_LINE_LENGTH)


STATUS_CSV_COLUMN = "status"
RUN_FOLDER_CSV_COLUMN = "run_folder"
WALLTIME_COLUMN = "walltime"

SUBMITTED_STATUS = "Submitted"
RUNNING_STATUS = "Running"
COMPLETED_STATUS = "Completed"
FAIL_STATUS = "Fail"
WHETHER_TO_RUN_COLUMN = "whether_to_run"


OUTPUT_CSV_KEY = "output_csv"
PATH_KEY = "path"
INITIAL_CSV_KEY = "initial_csv"
ROW_NUMBER_KEY = "row_number"  # row_number == 0 corresponds to
# row with column names
GDRIVE_FOLDER_KEY = "gdrive_storage_folder"
STDOUT_KEY = "stdout"
STDERR_KEY = "stderr"


# wandb
WANDB_URL_COLUMN = "WandB url"
WANDB_QUIET = True
WANDB_INIT_RETRIES = 100
WANDB_SLEEP_BETWEEN_INIT_RETRIES = 60
PROJECT_KEY = "project"


# # Tensorboard
# TB_CREDENTIALS_FIELDS = [
#     "refresh_token",
#     "token_uri",
#     "client_id",
#     "client_secret",
#     "scopes",
#     "type"
# ]
# TB_CREDENTIALS_DEFAULT = {
#     "scopes": [
#         "openid",
#         "https://www.googleapis.com/auth/userinfo.email"
#     ],
#     "type": "authorized_user"
# }
# TB_URL_COLUMN = "Tensorboard url"
# TB_LOG_FOLDER = "tb_log"
# TB_TIME_TO_LOG_LAST_EPOCH = 5
# TB_OUTPUT_BEFORE_LINK = "View your TensorBoard at: "
# TB_OUTPUT_AFTER_LINK = "\n"
# TB_OUTPUT_SIZE_LIMIT = 10 * 1024
# READ_BUFSIZE = 1024
# TENSORBOARD_FINISHED = "Total uploaded:"
# MAX_TIME_BETWEEN_TB_LOG_UPDATES = 60
# MAX_TIME_TO_WAIT_FOR_TB_TO_SAVE_DATA = 1800


LOGGING_CONFIG_KEY = "logging"


# gspread
DEFAULT_SPREADSHEET_ROWS = 100
DEFAULT_SPREADSHEET_COLS = 20
DEFAULT_SPREADSHEET_NAME = "default_spreadsheet"
DEFAULT_GAUTH_FOLDER = os.path.join(os.path.expanduser("~"), ".config", "gauth")
DEFAULT_GOOGLE_CREDENTIALS_PATH = os.path.join(
    DEFAULT_GAUTH_FOLDER, "credentials.json"
)
DEFAULT_GOOGLE_SERVICE_CREDENTIALS_PATH = os.path.join(
    DEFAULT_GAUTH_FOLDER, "service_key.json"
)
DEFAULT_REFRESH_GOOGLE_CREDENTIALS = os.path.join(
    DEFAULT_GAUTH_FOLDER, "gauth_refresh_credentials.json"
)
URL_ID_RE = re.compile(r"id=([a-zA-Z0-9-_]+)")
URL_KEY_RE = re.compile(r"key=([^&#]+)")
URL_SPREADSHEET_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")
URL_FILE_RE = re.compile(r"/file/d/([a-zA-Z0-9-_]+)")
URL_FOLDER_RE = re.compile(r"/folders/([a-zA-Z0-9-_]+)")
DEFAULT_GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.install",
    "https://www.googleapis.com/auth/drive.metadata",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
FILE_TYPES_ALLOWED_TO_SYNC = ("text/plain", "application/x-yaml")
SPREADSHEETS_URL = "https://docs.google.com/spreadsheets"
WORKSHEET_SEPARATOR = "::"
DELTA_PREFIX = "delta"
SLURM_PREFIX = "slurm"
PREFIX_SEPARATOR = ":"
OLD_PREFIX = "Old "
PREV_RUN_FOLDER_KEY = "prev_run_folder"
PLACEHOLDERS_FOR_DEFAULT = itself_and_lower_upper_case("Default")


DAEMON_SLEEP_TIME = 20
TIME_TO_LOSE_LOCK_IF_CONCURRENT = 0.1


if SYSTEM_PLATFORM == "darwin":
    try:
        mp.set_start_method("fork")
    except RuntimeError:
        # If start method is already set, verify it's 'fork'
        if mp.get_start_method() != "fork":
            raise RuntimeError(
                "Multiprocessing start method is not 'fork'. "
                "Current start method is: " + mp.get_start_method()
            )


def make_string_style(text_style, text_color):
    return (
        f"{CONTROL_PREFIX}{text_style}{CONTROL_SEPARATOR}"
        + f"{text_color}{CONTROL_SEPARATOR}"
        + f"{BLACK_COLOR_CODE}{CONTROL_SUFFIX}"
    )


def infer_logger_from_args(*args, **kwargs):
    # class with self.logger
    if hasattr(args[0], LOGGER_ARG_NAME):
        return getattr(args[0], LOGGER_ARG_NAME)

    # keyword logger
    if LOGGER_ARG_NAME in kwargs:
        return kwargs[LOGGER_ARG_NAME]

    # one of the unnamed args
    for arg in args:
        if isinstance(arg, BaseLogger):
            return arg

    return None


def retrier_factory_with_auto_logger(**retrier_factory_kwargs):
    return retrier_factory(
        logger="auto",
        infer_logger_from_args=infer_logger_from_args,
        **retrier_factory_kwargs,
    )


class BaseLogger:
    pass


# TODO(Alex | 13.07.2022) inherit from more sophisticated logger
class RedneckLogger(BaseLogger):
    def __init__(self, output_folder=None, retry_print=True):
        warnings.showwarning = self.get_warning_wrapper()

        if output_folder:
            self.update_output_folder(output_folder)
        else:
            self.output_folder = None
            self.stdout_file = None
            self.stderr_file = None

        self.retry_print = retry_print

        self.cache = {}
        self.csv_output = None
        self.tb_run = None
        self.wandb_run = None
        self.wandb_api = None
        self.gspread_client = None
        self.gdrive_client = None

        # gdrive logs sync
        self.gdrive_storage_folder_url = None
        self.remote_log_folder_url = None
        self.remote_stdout_url = None
        self.remote_stderr_url = None
        self.gdrive_daemon = None
        self.stdout_lock = None
        self.stderr_lock = None

    def store(self, name, msg):
        assert isinstance(msg, str)
        self.cache[name] = msg

    def dump(self, name):
        self.log("\n" + self.cache[name])

    def get_output_folder(self):
        return self.output_folder

    def update_output_folder(self, new_output_folder):
        self.output_folder = new_output_folder
        os.makedirs(new_output_folder, exist_ok=True)
        self.stdout_file = os.path.join(new_output_folder, "stdout.txt")
        self.stderr_file = os.path.join(new_output_folder, "stderr.txt")
        touch_file(self.stdout_file)
        touch_file(self.stderr_file)
        self.stdout_lock = make_file_lock(self.stdout_file)
        self.stderr_lock = make_file_lock(self.stderr_file)

    def get_gdrive_client(self):
        if self.gdrive_client is None:
            self.gdrive_client = make_gdrive_client(self)
        return self.gdrive_client

    def create_logs_on_gdrive(self, gdrive_storage_folder_url):
        assert self.output_folder

        self.gdrive_storage_folder_url = gdrive_storage_folder_url

        gdrive_client = self.get_gdrive_client()

        remote_run_folder = gdrive_client.create_node(
            os.path.basename(self.output_folder),
            node_type="folder",
            parent_folder_id=extract_id_from_gdrive_url(
                self.gdrive_storage_folder_url
            ),
        )
        remote_output = gdrive_client.create_node(
            "stdout", node_type="text", parent_folder_id=remote_run_folder["id"]
        )
        remote_stderr = gdrive_client.create_node(
            "stderr", node_type="text", parent_folder_id=remote_run_folder["id"]
        )
        self.remote_log_folder_url = remote_run_folder["embedLink"]
        self.remote_stdout_url = remote_output["embedLink"]
        self.remote_stderr_url = remote_stderr["embedLink"]

        return (
            self.remote_log_folder_url,
            self.remote_stdout_url,
            self.remote_stderr_url,
        )

    def start_gdrive_daemon(self, sync_time=DAEMON_SLEEP_TIME):
        def daemon_task(logger, sync_time):
            daemon_process = psutil.Process(os.getpid())

            while True:
                if daemon_process.parent() is not None:
                    sync_output_with_remote(logger)

                    time.sleep(sync_time)

                else:
                    sys.exit(0)

        assert self.remote_stdout_url
        assert self.remote_stderr_url

        self.gdrive_daemon = mp.Process(
            target=daemon_task, args=(self, sync_time)
        )
        self.gdrive_daemon.daemon = True
        self.gdrive_daemon.start()

    def set_csv_output(self, csv_output_config):
        self.csv_output = {}
        assert PATH_KEY in csv_output_config
        assert ROW_NUMBER_KEY in csv_output_config
        assert os.path.exists(csv_output_config[PATH_KEY])

        self.csv_output = copy.deepcopy(csv_output_config)
        if self.csv_output["spreadsheet_url"] is not None:
            self.gspread_client = make_gspread_client(
                self, DEFAULT_GOOGLE_CREDENTIALS_PATH
            )

    def log_csv(self, column_value_pairs):
        log_csv_for_concurrent(
            self.csv_output[PATH_KEY],
            [
                (self.csv_output[ROW_NUMBER_KEY], column_name, value)
                for column_name, value in column_value_pairs
            ],
            concurrent=False,
        )

    def log_separator(self):
        print(SEPARATOR)

        if self.stdout_file:
            print(SEPARATOR, file=open(self.stdout_file, "a"), flush=True)

    def progress(
        self,
        descripion,
        current_step,
        total_steps,
        frequency=PROGRESS_FREQUENCY,
    ):
        log_every_n_steps = (
            max(1, round(PROGRESS_FREQUENCY * total_steps))
            if frequency is not None
            else 1
        )
        if (
            current_step % log_every_n_steps == 0
            or current_step == 1
            or current_step == 2
            or current_step == total_steps
        ):
            self.log(
                "{} {}/{}: {}/100%..".format(
                    descripion,
                    current_step,
                    total_steps,
                    round(100 * float(current_step / total_steps)),
                ),
                carriage_return=(current_step != total_steps),
            )

    def log(self, msg, auto_newline=False, carriage_return=False):
        self.print_output(
            msg,
            LOG_PREFIX,
            prefix_style_code=make_string_style(
                BOLD_TEXT_STYLE, GREEN_COLOR_CODE
            ),
            message_style_code=make_string_style(
                BOLD_TEXT_STYLE, WHITE_COLOR_CODE
            ),
            output_file=self.stdout_file,
            output_file_lock=self.stdout_lock,
            auto_newline=auto_newline,
            carriage_return=carriage_return,
        )

    def info(self, msg, auto_newline=False, carriage_return=False):
        info_style_code = make_string_style(BOLD_TEXT_STYLE, PURPLE_COLOR_CODE)

        self.print_output(
            msg,
            INFO_PREFIX,
            prefix_style_code=info_style_code,
            message_style_code=info_style_code,
            output_file=self.stdout_file,
            output_file_lock=self.stdout_lock,
            auto_newline=auto_newline,
            carriage_return=carriage_return,
        )

    def error(self, msg, auto_newline=False, carriage_return=False):
        self.print_output(
            msg,
            ERROR_PREFIX,
            prefix_style_code=make_string_style(
                BOLD_TEXT_STYLE, RED_COLOR_CODE
            ),
            message_style_code=make_string_style(
                BOLD_TEXT_STYLE, WHITE_COLOR_CODE
            ),
            output_file=self.stderr_file,
            output_file_lock=self.stderr_lock,
            auto_newline=auto_newline,
            carriage_return=carriage_return,
        )

    def print_output(self, *args, **kwargs):
        if self.retry_print:
            self.print_output_with_retries(*args, **kwargs)
        else:
            self._print_output(*args, **kwargs)

    @retrier_factory_with_auto_logger()
    def print_output_with_retries(self, *args, **kwargs):
        self._print_output(*args, **kwargs)

    def _print_output(
        self,
        msg,
        prefix_keyword,
        prefix_style_code,
        message_style_code,
        output_file=None,
        output_file_lock=None,
        auto_newline=False,
        carriage_return=False,
    ):
        msg_prefix = "{} {}".format(get_current_time(), prefix_keyword)
        end_char = "" if carriage_return else "\n"
        print(
            self.make_log_message(
                msg,
                msg_prefix,
                prefix_style_code=prefix_style_code,
                message_style_code=message_style_code,
                auto_newline=auto_newline,
                carriage_return=carriage_return,
            ),
            flush=True,
            end=end_char,
        )

        if output_file:
            with (
                make_file_lock(output_file)
                if output_file_lock is None
                else output_file_lock
            ):
                print(
                    self.make_log_message(
                        msg,
                        msg_prefix,
                        prefix_style_code="",
                        message_style_code="",
                        auto_newline=auto_newline,
                        carriage_return=carriage_return,
                    ),
                    file=open(output_file, "a"),
                    flush=True,
                    end=end_char,
                )

    def make_log_message(
        self,
        msg,
        prefix,
        prefix_style_code="",
        message_style_code="",
        auto_newline=False,
        carriage_return=False,
    ):
        outside_style_code = ""
        if prefix_style_code:
            assert message_style_code
            outside_style_code = make_string_style(
                DEFAULT_TEXT_STYLE, WHITE_COLOR_CODE
            )
        return insert_char_before_max_width(
            "{}{}: {}{}{}".format(
                prefix_style_code,
                prefix,
                message_style_code,
                msg,
                outside_style_code,
            ),
            MAX_LINE_LENGTH if auto_newline else 0,
        ) + ("\r" if carriage_return else "")

    def get_warning_wrapper(self):
        def warning_wrapper(
            message, category, filename, lineno, file=None, line=None
        ):
            self.error(message, auto_newline=True)

        return warning_wrapper

    def finish_wandb(self, verbose=False):
        if self.wandb_run is not None:
            assert self.wandb_api is not None
            self.wandb_api.update()
            if verbose:
                self.log("Starting wandb finishing")
            self.wandb_run.finish(quiet=WANDB_QUIET)
            if verbose:
                self.log("wandb is finished")
            self.wandb_run = None

    def stop_gdrive_daemon(self):
        if self.gdrive_daemon:
            self.gdrive_daemon.terminate()
            self.gdrive_daemon.join()
            sync_output_with_remote(self)


def sync_output_with_remote(logger):
    assert logger.stdout_file
    assert logger.stderr_file
    assert logger.remote_stdout_url
    assert logger.remote_stderr_url
    assert logger.stdout_lock
    assert logger.stderr_lock

    gdrive_client = logger.get_gdrive_client()

    with NamedTemporaryFile("w+t", newline="") as tmp_file:
        for file, url, lock in [
            (logger.stdout_file, logger.remote_stdout_url, logger.stdout_lock),
            (logger.stderr_file, logger.remote_stderr_url, logger.stderr_lock),
        ]:
            with lock:
                shutil.copy(file, tmp_file.name)
            sync_local_file_with_gdrive(
                gdrive_client, tmp_file.name, url, download=False, logger=logger
            )


def make_logger(output_folder=None):
    return RedneckLogger(output_folder)


def make_logger_with_tmp_output_folder():
    tmp_output_folder = get_current_run_folder(
        DEFAULT_EXPERIMENT, DEFAULT_NAME_PREFIX
    )

    return make_logger(tmp_output_folder)


def update_and_move_logger_output_folder(
    logger, new_output_folder, require_old_folder=True
):
    if require_old_folder and logger.output_folder is None:
        raise Exception("Old logger output folder is None.")

    os.makedirs(new_output_folder, exist_ok=True)
    if logger.output_folder is not None:
        old_output_folder = logger.output_folder
        shutil.copytree(
            old_output_folder, new_output_folder, dirs_exist_ok=True
        )
        logger.stderr_lock = None
        logger.stdout_lock = None
        shutil.rmtree(old_output_folder)
    logger.update_output_folder(new_output_folder)


def store_profiler_results(logger, profiler):
    try:
        import torch

        memory_summary = torch.cuda.memory_summary()

    except Exception as e:
        logger.error(
            f"Torch is not installed. "
            f"Cannot get memory summary for profiler."
        )
        memory_summary = ""

    logger.store(
        "profiler_results", extract_profiler_results(profiler) + memory_summary
    )


def dump_profiler_results(logger):
    assert "profiler_results" in logger.cache
    logger.dump("profiler_results")


def handle_exception(logger, exception=None):
    if exception is None:
        logger.error("{}".format(traceback.format_exc()))
    else:
        logger.error("{}\n{}".format(str(exception), traceback.format_exc()))

    try_to_log_in_csv_in_batch(
        logger, [(STATUS_CSV_COLUMN, FAIL_STATUS), (WHETHER_TO_RUN_COLUMN, "1")]
    )

    try_to_sync_csv_with_remote(logger)
    if "profiler_results" in logger.cache:
        dump_profiler_results(logger)

    logger.finish_wandb()
    logger.stop_gdrive_daemon()
    sys.exit(1)


def try_to_log_in_csv(logger, column_name, value):
    try_to_log_in_csv_in_batch(logger, [(column_name, value)])


def try_to_log_in_csv_in_batch(logger, column_value_pairs):
    if logger.csv_output is not None:
        logger.log_csv(column_value_pairs)


def try_to_sync_csv_with_remote(logger, sync_row_zero=True):
    if logger.gspread_client is not None:
        worksheet_names = (
            [logger.csv_output["worksheet_name"]]
            if logger.csv_output["worksheet_name"] is not None
            else None
        )

        single_rows_per_csv = (
            [logger.csv_output[ROW_NUMBER_KEY]]
            if logger.csv_output[ROW_NUMBER_KEY] is not None
            else None
        )

        csv_files = [logger.csv_output[PATH_KEY]]
        spreadsheet_url = logger.csv_output["spreadsheet_url"]

        if single_rows_per_csv is not None and sync_row_zero:
            logger.gspread_client.upload_csvs_to_spreadsheet(
                spreadsheet_url,
                csv_files,
                worksheet_names=worksheet_names,
                single_rows_per_csv=[0],
            )

        logger.gspread_client.upload_csvs_to_spreadsheet(
            spreadsheet_url,
            csv_files,
            worksheet_names=worksheet_names,
            single_rows_per_csv=single_rows_per_csv,
        )

    elif logger.csv_output is not None:
        csv_row_to_edit = logger.csv_output[ROW_NUMBER_KEY]
        local_csv = read_csv_as_dict(logger.csv_output[PATH_KEY])
        row_col_value_triplets = [
            (csv_row_to_edit, col, value)
            for col, value in local_csv[csv_row_to_edit].items()
        ]
        log_csv_for_concurrent(
            logger.csv_output[INITIAL_CSV_KEY],
            row_col_value_triplets,
            concurrent=True,
        )


def try_to_log_in_wandb(logger, dict_to_log, step):
    wandb_run = logger.wandb_run
    if wandb_run is not None:
        if step < wandb_run.step:
            step = wandb_run.step + 1
        wandb_run.log(dict_to_log, step=step)


# def try_to_log_in_tb(
#     logger,
#     dict_to_log,
#     step,
#     step_offset=0,
#     flush=False,
#     text=False,
#     same_plot=False
# ):

#     if logger.tb_run:
#         if text:
#             for key, value in dict_to_log.items():
#                 if isinstance(value, dict):
#                     value = pretty_json(value)
#                 assert isinstance(value, str)
#                 logger.tb_run.add_text(key, value, global_step=step)
#         else:
#             tb_log(
#                 logger.tb_run,
#                 dict_to_log,
#                 step,
#                 step_offset=step_offset,
#                 flush=flush,
#                 same_plot=same_plot
#             )


def insert_char_before_max_width(
    input_string, max_width, char="\n", separator=" ", indent=INDENT
):
    if len(input_string) == 0 or max_width == 0:
        return input_string
    current_line = ""
    result = ""
    for word in input_string.split(separator):
        if current_line == "":
            current_line = word
        elif len(current_line) + len(word) <= max_width:
            current_line = current_line + separator + word
        else:
            result += current_line + char
            current_line = indent + word
    result += current_line
    return result


@contextlib.contextmanager
def redneck_logger_context(
    logging_config,
    log_folder,
    logger=None,
    exp_name="Default experiment",
    start_time=None,
    config_to_log_in_wandb=None,
):
    def set_up_local_csv(logger, output_config):
        csv_path = get_with_assert(output_config, PATH_KEY)
        if not os.path.exists(csv_path):
            touch_file(csv_path)
        local_csv_path = os.path.join(
            logger.output_folder, "local_copy_" + os.path.basename(csv_path)
        )
        with make_file_lock(csv_path):
            shutil.copy(csv_path, local_csv_path)
        output_config[INITIAL_CSV_KEY] = output_config[PATH_KEY]
        output_config[PATH_KEY] = local_csv_path
        logger.set_csv_output(output_config)

    if start_time is None:
        start_time = get_current_time()

    if logger is None:
        logger = make_logger(output_folder=log_folder)
    elif logger.output_folder != log_folder:
        update_and_move_logger_output_folder(
            logger, new_output_folder=log_folder, require_old_folder=False
        )

    logger.log("Hostname: {}".format(get_hostname()))
    logger.log("Process id: {}".format(os.getpid()))
    for job_id_var in ["SLURM_JOB_ID", "CONDOR_JOB_ID"]:
        job_id = os.environ.get(job_id_var)
        if job_id is not None:
            break
    if job_id is None:
        job_id = "Not found"
    logger.log("job_id: {}".format(job_id))

    # add csv folder if exists
    if OUTPUT_CSV_KEY in logging_config:
        output_config = logging_config[OUTPUT_CSV_KEY]
        set_up_local_csv(logger, output_config)
        logger.log(f"Output_config:\n{logger.csv_output}", auto_newline=True)
        try_to_log_in_csv_in_batch(
            logger,
            [
                (WHETHER_TO_RUN_COLUMN, "0"),
                (STATUS_CSV_COLUMN, RUNNING_STATUS),
                (RUN_FOLDER_CSV_COLUMN, os.path.dirname(logger.stdout_file)),
                ("job id", job_id),
            ],
        )

    # set up google drive sync
    if logging_config.get(GDRIVE_FOLDER_KEY) is not None:
        logger.create_logs_on_gdrive(logging_config[GDRIVE_FOLDER_KEY])
        logger.start_gdrive_daemon()
        logger.log(f"Remote folder with logs: {logger.remote_log_folder_url}")
        try_to_log_in_csv_in_batch(
            logger,
            [
                (STDOUT_KEY, logger.remote_stdout_url),
                (STDERR_KEY, logger.remote_stderr_url),
            ],
        )

    # use_tb = get_with_assert(logging_config, "use_tb")
    use_tb = logging_config.get("use_tb", False)
    tb_log_dir = None
    tb_upload = False
    if use_tb:
        raise Exception("Tensorboard is not supported.")
        # tb_log_dir = os.path.join(
        #     log_folder,
        #     TB_LOG_FOLDER
        # )

    # use_wandb = get_with_assert(logging_config, "use_wandb")
    use_wandb = logging_config.get("use_wandb", False)
    # init wandb_run if exists
    if use_wandb:
        wandb_config = logging_config["wandb"]
        wandb_dir = os.path.join(
            get_system_root_path(),
            "tmp",
            f"wandb_{get_hostname()}_{os.getpid()}",
        )
        os.makedirs(wandb_dir, exist_ok=True)
        if use_tb and wandb_config.get("sync_tb", False):
            raise Exception("Wandb tensorboard patch is not supported.")

        logger.wandb_run, logger.wandb_api = init_wandb_run(
            wandb_config,
            exp_name,
            wandb_dir=wandb_dir,
            config=config_to_log_in_wandb,
            logger=logger,
        )
        # extract wandb link
        wandb_url = logger.wandb_run.get_url()
        try_to_log_in_csv(logger, WANDB_URL_COLUMN, wandb_url)
        logger.log("WandB url: {}".format(wandb_url))

    # init tb run if exists
    if use_tb:
        raise Exception("Tensorboard is not supported.")
        # tb_config = logging_config["tb"]
        # tb_upload = tb_config["upload_online"]
        # assert_tb_credentials(tb_config["credentials_path"])
        # assert tb_log_dir is not None

        # logger.tb_run = torch_tensorboard.SummaryWriter(tb_log_dir)

        # tb_process_spawner = prepare_factory_without_args(
        #     run_tb_folder_listener,
        #     log_folder=log_folder,
        #     exp_name=exp_name,
        #     description=(
        #         "Run path: {}".format(
        #             log_folder
        #         )
        #     )
        # )

    # tell that logger is created
    logger.log("Logger context initialized!")
    try_to_sync_csv_with_remote(logger)
    yield logger

    if use_tb:
        # logger.tb_run.close()

        raise Exception("Tensorboard is not supported.")

        # if tb_upload:
        #     raise Exception("Tensorboard is not supported.")
        # logger.log("Making sure that tensorboard folder is synced.")
        # tb_log_folder_still_updating = folder_still_has_updates(
        #     tb_log_dir,
        #     MAX_TIME_BETWEEN_TB_LOG_UPDATES,
        #     MAX_TIME_TO_WAIT_FOR_TB_TO_SAVE_DATA,
        #     check_time=None
        # )
        # if tb_log_folder_still_updating is None:
        #     logger.error(
        #         f"Failed to start watchdog folder observer "
        #         f"for tensorboard log folder."
        #         f"Most probably: \"[Errno 28] inotify watch limit reached\""
        #     )
        # elif tb_log_folder_still_updating:
        #     logger.error(
        #         f"Tensorboard was updating {tb_log_dir} "
        #         f"longer than {MAX_TIME_TO_WAIT_FOR_TB_TO_SAVE_DATA} "
        #         f"(time between folder updates was "
        #         f"at most {MAX_TIME_BETWEEN_TB_LOG_UPDATES})"
        #     )
        # logger.log("Checking \"tensorboard dev upload\" output.")
        # # extract tb link
        # tb_url = get_tb_url(logger, tb_process_spawner)
        # # insert tb link in csv if exists
        # try_to_log_in_csv(
        #     logger,
        #     TB_URL_COLUMN,
        #     tb_url
        # )
        # logger.log("Tensorboard url: {}".format(tb_url))
        # logger.tb_run = None

        # try_to_sync_csv_with_remote(logger)

    # close wandb
    logger.finish_wandb(verbose=True)

    try_to_log_in_csv_in_batch(
        logger,
        [
            (WALLTIME_COLUMN, str((get_current_time() - start_time))),
            (STATUS_CSV_COLUMN, COMPLETED_STATUS),
            (WHETHER_TO_RUN_COLUMN, "0"),
        ],
    )
    logger.log("Final log line for remote logs!")
    try_to_sync_csv_with_remote(logger)
    logger.stop_gdrive_daemon()
    logger.log("Logger context cleaned!")


# def assert_tb_credentials(credentials_path):

#     def assert_field(field_name, credentials_dict):
#         assert field_name in credentials_dict
#         if field_name in TB_CREDENTIALS_DEFAULT:
#             assert credentials_dict[field_name] \
#                 == TB_CREDENTIALS_DEFAULT[field_name]
#         else:
#             assert isinstance(credentials_dict[field_name], str)
#             assert len(credentials_dict[field_name])

#     assert os.path.exists(credentials_path)

#     credentials = read_json(credentials_path)
#     for field in TB_CREDENTIALS_FIELDS:
#         assert_field(field, credentials)


# def run_tb_folder_listener(
#     log_folder,
#     exp_name,
#     description=None
# ):

#     cmd_as_list = [
#         "tensorboard",
#         "dev",
#         "upload",
#         "--logdir",
#         os.path.join(log_folder, TB_LOG_FOLDER),
#         "--name",
#         exp_name
#     ]

#     if description is not None:
#         cmd_as_list += ["--description", description]

#     proc = subprocess.Popen(
#         cmd_as_list,
#         stdout=subprocess.PIPE,
#         stderr=subprocess.PIPE
#     )

#     return proc


# def get_tb_url(logger, tb_process_spawner):

#     def read_proc_output(stream, total_output_size):

#         size_read_so_far = 0
#         result = ""

#         while (
#             stream
#                 and size_read_so_far < total_output_size
#                 and not TENSORBOARD_FINISHED in result
#         ):

#             result += stream.read(READ_BUFSIZE).decode("utf-8")
#             size_read_so_far += READ_BUFSIZE

#         return result

# def extract_link(output, logger):

#     def assert_in_output(expected_string, output):
#         assert expected_string in output, \
#             "Expected \"{}\" in output:\n{}".format(
#                 expected_string,
#                 output
#             )

#     assert_in_output(TB_OUTPUT_BEFORE_LINK, output)
#     assert_in_output(TB_OUTPUT_AFTER_LINK, output)
#     result = output.split(TB_OUTPUT_BEFORE_LINK)[1]
#     return result.split(TB_OUTPUT_AFTER_LINK)[0]

# def final_func(logger):
#     logger.error(
#         "Could not get a tb link.\nReason: {}".format(
#             traceback.format_exc()
#         )
#     )
#     return None

# @retrier_factory(logger, final_func)
# def try_to_extract_link(tb_process_spawner):

#     tb_proc = tb_process_spawner()

#     out = read_proc_output(tb_proc.stdout, TB_OUTPUT_SIZE_LIMIT)

#     if tb_proc.poll() is None:
#         # process is alive
#         kill_processes([tb_proc.pid], logger)
#     else:
#         err = read_proc_output(tb_proc.stderr, TB_OUTPUT_SIZE_LIMIT)
#         if err:
#             logger.error(err)

#     assert TENSORBOARD_FINISHED in out

#     tb_url = extract_link(out, logger)

#     return tb_url

# tb_url = try_to_extract_link(tb_process_spawner)

# return tb_url


def delete_run_folders(inputs_csv):
    inputs_as_dict = read_csv_as_dict(inputs_csv)
    for row in inputs_as_dict.values():
        assert RUN_FOLDER_CSV_COLUMN in row
        run_folder_path = row[RUN_FOLDER_CSV_COLUMN]
        if os.path.exists(run_folder_path):
            shutil.rmtree(run_folder_path)


# def tb_log(
#     tb_run,
#     stats_dict,
#     current_step,
#     step_offset=0,
#     flush=False,
#     skip_key_func=None,
#     same_plot=False
# ):
#     def assert_scalar(value):
#         assert is_number(value), \
#                 "Only scalars are supported for tensorboard."

#     def log_stat_func_wrapper(tb_run, nested_key_as_list, step):

#         def log_stat_for_given_args(value):
#             stat_name = ".".join(nested_key_as_list)
#             assert_scalar(value)

#             tb_run.add_scalar(stat_name, value, global_step=step)
#             return value

#         return log_stat_for_given_args

#     def log_multiple_curves(tb_run, stats_dict, step):

#         assert is_nested_dict(stats_dict)

#         for plot_name, curves_dict in stats_dict.items():

#             assert not is_nested_dict(curves_dict)

#             for value in curves_dict.values():
#                 assert_scalar(value)

#                 tb_run.add_scalars(
#                     plot_name,
#                     curves_dict,
#                     global_step=step
#                 )

#     step = current_step + step_offset

#     if same_plot:

#         log_multiple_curves(tb_run, stats_dict, step)

#     else:

#         dict_leaves_as_nested_keys = get_leaves_of_nested_dict(stats_dict)

#         for nested_key_as_list in dict_leaves_as_nested_keys:

#             assert len(nested_key_as_list)
#             if skip_key_func is not None and skip_key_func(nested_key_as_list):
#                 continue

#             apply_func_to_dict_by_nested_key(
#                 stats_dict,
#                 nested_key_as_list,
#                 func=log_stat_func_wrapper(tb_run, nested_key_as_list, step)
#             )

#     if flush:
#         tb_run.flush()


def extract_id_from_spreadsheet_url(spreadsheet_url):
    return extract_by_regex_from_url(
        spreadsheet_url, [URL_KEY_RE, URL_SPREADSHEET_RE]
    )


def extract_id_from_gdrive_url(gdrive_url):
    return extract_by_regex_from_url(
        gdrive_url, [URL_ID_RE, URL_KEY_RE, URL_FILE_RE, URL_FOLDER_RE]
    )


def extract_by_regex_from_url(url, regexes):
    for regex in regexes:
        match = regex.search(url)
        if match:
            return match.group(1)

    raise Exception(f"No valid key found in URL: {url}.")


class GspreadClient:
    def __init__(self, logger, gspread_credentials):
        self.logger = logger
        self.gspread_credentials = gspread_credentials
        self.client = self._create_client()

    @retrier_factory_with_auto_logger()
    def _create_client(self):
        if os.path.exists(DEFAULT_GOOGLE_SERVICE_CREDENTIALS_PATH):
            return gspread.service_account(
                filename=DEFAULT_GOOGLE_SERVICE_CREDENTIALS_PATH
            )

        _, auth_user_filename = make_google_auth(
            self.gspread_credentials, logger=self.logger
        )
        return gspread.oauth(
            credentials_filename=self.gspread_credentials,
            authorized_user_filename=auth_user_filename,
        )

    @retrier_factory_with_auto_logger()
    def delete_spreadsheet(self, spreadsheet_url):
        assert self.client
        self.client.del_spreadsheet(
            extract_id_from_spreadsheet_url(spreadsheet_url)
        )

    @retrier_factory_with_auto_logger()
    def get_spreadsheet_by_url(self, spreadsheet_url):
        if spreadsheet_url is None:
            spreadsheet = self.client.create(
                DEFAULT_SPREADSHEET_NAME + "_" + str(get_current_time())
            )

            return spreadsheet
        else:
            return self.client.open_by_url(spreadsheet_url)

    @retrier_factory_with_auto_logger()
    def upload_csvs_to_spreadsheet(
        self,
        spreadsheet_url,
        csv_files,
        worksheet_names=None,
        single_rows_per_csv=None,
    ):
        def assert_list(value):
            assert isinstance(value, list), f"Expected list instead of {value}"

        assert_list(csv_files)
        if worksheet_names is not None:
            assert_list(worksheet_names)
        if single_rows_per_csv is not None:
            assert_list(single_rows_per_csv)
            assert len(single_rows_per_csv) == len(csv_files)

        new_spreadsheet = False
        if spreadsheet_url is None:
            new_spreadsheet = True

        spreadsheet = self.get_spreadsheet_by_url(spreadsheet_url)

        existing_worksheets = list(spreadsheet.worksheets())
        first_worksheet = existing_worksheets[0]
        existing_worksheets = list(
            worksheet.title for worksheet in existing_worksheets
        )

        if new_spreadsheet:
            worksheet_names = []
            for csv_file_path in csv_files:
                worksheet_names.append(
                    extract_csv_name_from_path(csv_file_path)
                )
        elif worksheet_names is None:
            worksheet_names = existing_worksheets

        existing_worksheets = set(existing_worksheets)

        assert len(worksheet_names) == len(csv_files)

        removed_default_worksheet = False

        for i in range(len(csv_files)):
            csv_file_path = csv_files[i]
            worksheet_name = worksheet_names[i]

            single_row = None
            if single_rows_per_csv is not None:
                single_row = single_rows_per_csv[i]

            with make_file_lock(csv_file_path):
                if not worksheet_name in existing_worksheets:
                    spreadsheet.add_worksheet(
                        title=worksheet_name,
                        rows=DEFAULT_SPREADSHEET_ROWS,
                        cols=DEFAULT_SPREADSHEET_COLS,
                    )
                    existing_worksheets.add(worksheet_name)

                if (
                    new_spreadsheet
                    and worksheet_name != first_worksheet
                    and not removed_default_worksheet
                ):
                    assert len(existing_worksheets) == 2
                    spreadsheet.del_worksheet(first_worksheet)
                    removed_default_worksheet = True

                csv_file_as_list = list(csv.reader(open(csv_file_path)))

                a1_range_to_update = worksheet_name
                if single_row is not None:
                    gsheets_row = str(single_row + 1)
                    a1_range_to_update += "!" + gsheets_row + ":" + gsheets_row
                    csv_file_as_list = [csv_file_as_list[single_row]]

                spreadsheet.values_update(
                    a1_range_to_update,
                    params={"valueInputOption": "USER_ENTERED"},
                    body={"values": csv_file_as_list},
                )

        return spreadsheet.url

    @retrier_factory_with_auto_logger()
    def download_spreadsheet_as_csv(
        self,
        spreadsheet_url,
        folder_for_csv,
        worksheet_names=None,
        downloaded_files_prefix="",
    ):
        os.makedirs(folder_for_csv, exist_ok=True)

        spreadsheet = self.get_spreadsheet_by_url(spreadsheet_url)

        worksheets_dict = build_spreadsheet_dict(spreadsheet, worksheet_names)

        result = []
        for name, sheet in worksheets_dict.items():
            df = pd.DataFrame(sheet.get_all_values())

            df.rename(columns=df.iloc[0], inplace=True)
            df.drop(df.index[0], inplace=True)
            csv_path = os.path.join(
                folder_for_csv, downloaded_files_prefix + name + ".csv"
            )
            df.to_csv(csv_path, index=False)
            result.append(csv_path)

        return result


def make_gspread_client(
    logger, gspread_credentials=DEFAULT_GOOGLE_CREDENTIALS_PATH
):
    return GspreadClient(logger, gspread_credentials=gspread_credentials)


def build_spreadsheet_dict(spreadsheet, worksheet_names):
    if worksheet_names is None:
        worksheets_dict = {
            worksheet.title: worksheet for worksheet in spreadsheet.worksheets()
        }

    else:
        worksheets_dict = {
            worksheet_name: spreadsheet.worksheet(worksheet_name)
            for worksheet_name in worksheet_names
        }

    return worksheets_dict


def extract_csv_name_from_path(csv_file_path):
    assert ".csv" in csv_file_path
    return os.path.basename(csv_file_path).replace(".csv", "")


@retrier_factory_with_auto_logger(
    max_retries=WANDB_INIT_RETRIES, sleep_time=WANDB_SLEEP_BETWEEN_INIT_RETRIES
)
def init_wandb_run(wandb_config, exp_name, wandb_dir, config, logger):
    wandb_password = get_value_from_config(
        wandb_config["netrc_path"], "password"
    )

    wandb.login(key=wandb_password)

    settings = None
    if SYSTEM_PLATFORM == "linux":
        settings = wandb.Settings(start_method="fork")
    wandb_init_kwargs = wandb_config.get("wandb_init_kwargs", {})
    if PROJECT_KEY not in wandb_init_kwargs:
        wandb_init_kwargs[PROJECT_KEY] = exp_name
    run = wandb.init(
        dir=wandb_dir,
        settings=settings,
        sync_tensorboard=wandb_config.get("sync_tb", False),
        config=config,
        **wandb_init_kwargs,
    )
    api = wandb.Api(api_key=wandb_password).run(run.path)
    return run, api


class GdriveClient:
    def __init__(self, logger, credentials_file):
        self.logger = logger

        self.credentials = credentials_file

        self.client = self._create_client()

    @retrier_factory_with_auto_logger()
    def _create_client(self):
        if os.path.exists(DEFAULT_GOOGLE_SERVICE_CREDENTIALS_PATH):
            settings = {
                "client_config_backend": "service",
                "service_config": {
                    "client_json_file_path": DEFAULT_GOOGLE_SERVICE_CREDENTIALS_PATH,
                },
            }
            gauth = GoogleAuth(settings=settings)
            gauth.ServiceAuth()
        else:
            gauth, _ = make_google_auth(self.credentials)
        return GoogleDrive(gauth)

    def get_node_by_id(self, node_id):
        return self.client.CreateFile({"id": node_id})

    def create_node(self, node_name, node_type, parent_folder_id=None):
        metadata = {"title": node_name}

        if node_type == "text":
            metadata["mimeType"] = "text/plain"
        elif node_type == "folder":
            metadata["mimeType"] = "application/vnd.google-apps.folder"
        else:
            raise_unknown("node type", node_type, "GdriveClient.create_node()")

        if parent_folder_id is not None:
            metadata["parents"] = [
                {"kind": "drive#fileLink", "id": parent_folder_id}
            ]

        new_node = self.client.CreateFile(metadata=metadata)

        new_node.Upload()

        return new_node


def make_gdrive_client(
    logger, credentials_file=DEFAULT_GOOGLE_CREDENTIALS_PATH
):
    return GdriveClient(logger, credentials_file=credentials_file)


def make_google_auth(
    credentials_json,
    auth_user_json_path=DEFAULT_REFRESH_GOOGLE_CREDENTIALS,
    scopes=DEFAULT_GOOGLE_SCOPES,
    logger=None,
):
    def do_gauth(settings):
        gauth = GoogleAuth(settings=settings)
        gauth.CommandLineAuth()
        return gauth

    credentials = read_json(credentials_json)["installed"]

    settings = {
        "client_config_backend": "settings",
        "client_config": {
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
        },
        "save_credentials": True,
        "save_credentials_backend": "file",
        "save_credentials_file": auth_user_json_path,
        "get_refresh_token": True,
        "oauth_scope": scopes,
    }

    try:
        gauth = do_gauth(settings)
    except RefreshError:
        log_or_print(
            "GAUTH token needs to be refreshed. Removing old one.", logger
        )
        remove_file_or_folder(auth_user_json_path)
        gauth = do_gauth(settings)

    return gauth, auth_user_json_path


@retrier_factory_with_auto_logger()
def sync_local_file_with_gdrive(
    gdrive_client, local_filepath, remote_url, download=False, logger=None
):
    remote_file = get_gdrive_file_by_url(gdrive_client, remote_url)

    if "mimeType" in remote_file:
        assert remote_file["mimeType"] in FILE_TYPES_ALLOWED_TO_SYNC

    if download:
        remote_file.GetContentFile(local_filepath)
    else:
        remote_file.SetContentFile(local_filepath)
        remote_file.Upload()
    return remote_file


def get_gdrive_file_by_url(gdrive_client, remote_url):
    file_id = extract_id_from_gdrive_url(remote_url)
    return gdrive_client.get_node_by_id(file_id)


def log_csv_for_concurrent(csv_path, row_col_value_triplets, concurrent=True):
    if concurrent:
        lock = make_file_lock(csv_path)
        row_col_value_triplets_clean = []
    else:
        lock = NULL_CONTEXT
    remove_chars = [QUOTE_CHAR]

    with lock:
        for csv_row_number, column_name, value in row_col_value_triplets:
            column_name = as_str_for_csv(column_name, remove_chars)
            value = as_str_for_csv(value, remove_chars)
            if concurrent:
                row_col_value_triplets_clean.append(
                    (csv_row_number, column_name, value)
                )

            write_into_csv_with_column_names(
                csv_path,
                csv_row_number,
                column_name,
                value,
                replace_nulls=True,
                use_lock=False,
            )

    if concurrent:
        time.sleep(TIME_TO_LOSE_LOCK_IF_CONCURRENT)
        with lock:
            csv_as_dict = read_csv_as_dict(csv_path)

        for csv_row_number, column_name, value in row_col_value_triplets_clean:
            found_value = csv_as_dict.get(csv_row_number, {}).get(column_name)
            if is_number(value):
                assert is_number(found_value)
                value = float(value)
                found_value = float(found_value)
            # assert_two_values_are_close(
            #     found_value,
            #     value
            # )
            assert value == found_value, (
                f"Value {value} is not equal to found value {found_value} "
                f"for column {column_name} in file {csv_path}."
            )


class RedneckProgressBar:
    def __init__(self, total_steps, description="", logger=None):
        self.logger = logger
        self.description = description
        self.total_steps = total_steps
        self.current_step = 0

    def update(self):
        self.current_step += 1
        if self.logger is None:
            print(
                f"{self.description}: "
                f"{self.current_step}/{self.total_steps}"
            )
        else:
            self.logger.progress(
                self.description, self.current_step, self.total_steps
            )


def make_progress_bar(total_steps, description="", logger=None):
    return RedneckProgressBar(total_steps, description, logger)


def fetch_csv(csv_path, logger, downloaded_file_prefix=""):
    spreadsheet_url = None
    worksheet_name = None
    gspread_client = None

    if SPREADSHEETS_URL in csv_path:
        if WORKSHEET_SEPARATOR in csv_path:
            csv_path_split = csv_path.split(WORKSHEET_SEPARATOR)
            assert len(csv_path_split) == 2
            spreadsheet_url = csv_path_split[0]
            worksheet_name = csv_path_split[1]
            worksheet_names = [worksheet_name]
        else:
            spreadsheet_url = csv_path
            worksheet_names = None

        gspread_client = make_gspread_client(logger)

        csv_paths = gspread_client.download_spreadsheet_as_csv(
            spreadsheet_url,
            os.path.join(
                get_default_csv_folder(),
                spreadsheet_url.split("edit#gid")[0].replace(os.sep, "(slash)"),
            ),
            worksheet_names=worksheet_names,
            downloaded_files_prefix=downloaded_file_prefix,
        )
        assert len(csv_paths) == 1
        csv_path = csv_paths[0]

    if worksheet_name is None:
        worksheet_name = os.path.basename(csv_path)

    return csv_path, spreadsheet_url, worksheet_name, gspread_client


def get_default_csv_folder():
    return os.path.join(get_project_root_path(), "inputs")


def try_to_upload_csv(
    csv_path, spreadsheet_url, worksheet_name, gspread_client
):
    if gspread_client is not None:
        gspread_client.upload_csvs_to_spreadsheet(
            spreadsheet_url,
            csv_files=[csv_path],
            worksheet_names=[worksheet_name],
        )


def make_prefixed_column_name(name, prefix):
    return prefix + PREFIX_SEPARATOR + name


def make_delta_column_name(name):
    return make_prefixed_column_name(name, DELTA_PREFIX)


def make_slurm_column_name(name):
    return make_prefixed_column_name(name, SLURM_PREFIX)


# def log_info(logger, tensor, name):
#     if logger is None:
#         logger = make_logger()
#     logger.log(f"{name} norm: {torch.linalg.norm(tensor)}")
#     cumsums = compute_tensor_cumsums(tensor)
#     for dim_i in range(len(cumsums)):
#         logger.log(
#             f"{name} norm of cumsum for dim: {dim_i}: "
#             f"{cumsums[dim_i]}"
#         )
