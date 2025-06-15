import os
import sys
import re


# local modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from stnd.utility.utils import (
    NEW_SHELL_INIT_COMMAND,
    get_with_assert,
    run_cmd_through_popen,
)
from stnd.utility.logger import try_to_log_in_csv

sys.path.pop(0)


def patch_runner_config(experiment_config):
    pass


def check_runner_config(experiment_config, config_path, logger=None):
    pass


def make_buffer_processor(logger, experiment_config):
    take_last_dict = experiment_config.get("take_last_dict", None)
    if take_last_dict is None:
        return None
    else:
        take_last_dict = {k: re.compile(v) for k, v in take_last_dict.items()}

    def buffer_processor(buffer):
        for col_name, regex in take_last_dict.items():
            search_res = re.findall(regex, buffer)
            if len(search_res) > 0:
                extracted_value = search_res[-1]
                try_to_log_in_csv(logger, col_name, extracted_value)

    return buffer_processor


def runner(experiment_config, logger=None, processes_to_kill_before_exiting=[]):
    cmd_to_run = make_task_cmd(
        get_with_assert(experiment_config, "exec_path"),
        experiment_config.get("kwargs"),
        experiment_config.get("two_dash_flags"),
        experiment_config.get("single_dash_flags"),
        experiment_config.get("is_python", True),
        experiment_config.get("is_bash", False),
        get_with_assert(experiment_config, "conda_env"),
        logger=logger,
    )

    stdout_buffer_processor = make_buffer_processor(logger, experiment_config)

    logger.log(f"Running command:\n{cmd_to_run}", auto_newline=True)
    logger.log(f"As one line:\n{cmd_to_run}", auto_newline=False)
    run_cmd_through_popen(
        cmd_to_run,
        logger,
        stdout_buffer_processor=stdout_buffer_processor,
    )


def make_task_cmd(
    exec_path,
    kwargs,
    two_dash_flags,
    single_dash_flags,
    is_python,
    is_bash,
    conda_env,
    logger,
):
    if kwargs is not None:
        kwargs_str = " " + " ".join(
            ["--{}={}".format(k, v) for k, v in kwargs.items()]
        )
    else:
        kwargs_str = ""

    if two_dash_flags is not None:
        two_dash_flags_str = " " + " ".join(
            ["--{}".format(arg) for arg in two_dash_flags]
        )
    else:
        two_dash_flags_str = ""

    if single_dash_flags is not None:
        single_dash_flags_str = " " + " ".join(
            ["-{}".format(arg) for arg in single_dash_flags]
        )
    else:
        single_dash_flags_str = ""

    if conda_env is not None:
        conda_cmd = "{} {} && ".format(NEW_SHELL_INIT_COMMAND, conda_env)
    else:
        conda_cmd = ""

    if is_python:
        python_cmd = "python "
    else:
        python_cmd = ""

    if is_bash:
        bash_cmd = "bash "
    else:
        bash_cmd = ""

    return (
        conda_cmd
        + python_cmd
        + bash_cmd
        + exec_path
        + kwargs_str
        + two_dash_flags_str
        + single_dash_flags_str
    )
