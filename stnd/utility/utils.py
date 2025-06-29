# import torch
import numpy as np
import random
import os
import yaml
import copy
from datetime import datetime
import subprocess

# from deepdiff import DeepDiff, model as dd_model
from hashlib import blake2b, md5
import pickle
import shutil
import socket
import traceback
import yaml
from tempfile import NamedTemporaryFile
import csv
from filelock import FileLock
import json
import time
import signal
import platform
import sys
from collections import Counter
from collections.abc import Iterable
import itertools
import contextlib

# from watchdog.observers import Observer
# from watchdog.events import FileSystemEventHandler
import io
import re

# import matplotlib.pyplot as plt
import pandas as pd
import threading

# import gdown
from urllib.parse import urlparse
import requests


MAX_BUFFER_SIZE = 1000
SYSTEM_PLATFORM = platform.system().lower()
DEFAULT_HASH_SIZE = 10
DEFAULT_EXPERIMENTS_FOLDER = "experiments"
PROFILER_GROUP_BY_STACK_N = 5
PROFILER_OUTPUT_ROW_LIMIT = 10
DEFAULT_FILE_CHUNK_SIZE = 4096
EMPTY_CSV_TOKEN = "?"
DEFAULT_ENV_NAME = os.environ.get("DEFAULT_ENV", None)
TEST_ENV_NAME = os.environ.get("TEST_ENV", None)
BASHRC_PATH = os.path.join(
    os.environ["HOME"], (".zshrc" if SYSTEM_PLATFORM == "darwin" else ".bashrc")
)
NEW_SHELL_INIT_COMMAND = "source {} && conda activate".format(BASHRC_PATH)
FLOATING_POINT = "."
NAME_SEP = "_"
NAME_NUMBER_SEPARATOR = "-"
NULL_CONTEXT = contextlib.nullcontext()
PROJECT_ROOT_ENV_NAME = "PROJECT_ROOT_PROVIDED_FOR_STUNED"


DEFAULT_SLEEP_TIME = 10
DEFAULT_NUM_ATTEMTPS = 10
MAX_RETRIES_ERROR_MSG = "Maximum number of retries failed."


DEFAULT_INDENT_IN_JSON = 2


LIST_START_SYMBOL = "["
LIST_END_SYMBOL = "]"
DELIMETER = ","
QUOTE_CHAR = '"'
ESCAPE_CHAR = "\\"
INF = float("Inf")
TOL = 1e6
EXPONENTIAL_SYMBOLS = ("e", "E")


# matplotlib
PLT_ROW_SIZE = 4
PLT_COL_SIZE = 4
PLT_PLOT_HEIGHT = 5
PLT_PLOT_WIDTH = 5


# regexes
ENV_VAR_RE = re.compile(r"<\$([a-zA-Z0-9-_]+)>")


class ChildrenForPicklingPreparer:
    def _prepare_for_pickling(self):
        for attr_name in object_attributes(self):
            prepare_for_pickling(getattr(self, attr_name))

    def _prepare_for_unpickling(self):
        for attr_name in object_attributes(self):
            prepare_for_unpickling(getattr(self, attr_name))


def object_attributes(obj):
    return filter(lambda a: not a.startswith("__"), dir(obj))


def read_yaml(yaml_file):
    with open(yaml_file, "r") as stream:
        return yaml.safe_load(stream)


def apply_random_seed(random_seed):
    assert is_number(random_seed)
    random_seed = int(parse_float_or_int_from_string(str(random_seed)))
    random.seed(random_seed)
    np.random.seed(random_seed)

    try:
        import torch

        torch.manual_seed(random_seed)
        torch.cuda.manual_seed(random_seed)
        torch.cuda.manual_seed_all(random_seed)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"  # to suppress warning
        torch.use_deterministic_algorithms(True, warn_only=True)
    except ImportError:
        print("PyTorch is not installed, skipping seeding")
        pass


def get_current_time():
    return datetime.now()


def raise_unknown(param, value, location=""):
    exception_msg = "Unknown {}".format(param)
    if location:
        exception_msg += " in {}".format(location)
    exception_msg += ": {}".format(value)
    raise Exception(exception_msg)


def append_dict(total_dict, current_dict, allow_new_keys=False):
    """
    Append leaves of possibly nested <current_dict>
    to leaf lists of possibly nested <total_dict>
    """

    def to_create_new_key(is_new_total_dict, allow_new_keys, key, total_dict):
        return is_new_total_dict or (allow_new_keys and key not in total_dict)

    is_new_total_dict = False
    if len(total_dict) == 0:
        is_new_total_dict = True
    for key, value in current_dict.items():
        if isinstance(value, dict):
            if to_create_new_key(
                is_new_total_dict, allow_new_keys, key, total_dict
            ):
                sub_dict = {}
                append_dict(sub_dict, value, allow_new_keys=allow_new_keys)
                total_dict[key] = sub_dict
            else:
                assert key in total_dict
                sub_dict = total_dict[key]
                assert isinstance(sub_dict, dict)
                append_dict(sub_dict, value, allow_new_keys=allow_new_keys)
                total_dict[key] = sub_dict
        else:
            if to_create_new_key(
                is_new_total_dict, allow_new_keys, key, total_dict
            ):
                total_dict[key] = [value]
            else:
                assert key in total_dict
                assert isinstance(total_dict[key], list)
                total_dict[key].append(value)


def check_element_in_iterable(
    iterable,
    element,
    element_name="element",
    iterable_name="iterable",
    reference=None,
    raise_if_wrong=True,
):
    element_in_iterable = element in iterable
    if raise_if_wrong:
        try:
            assert element_in_iterable
        except Exception as e:
            exception_msg = 'No {} "{}" in {}:\n{}'.format(
                element_name, element, iterable_name, iterable
            )
            if reference is not None:
                exception_msg += "\nFor:\n {}".format(reference)
            raise Exception(exception_msg)
    return element_in_iterable


def check_dict(
    dict,
    required_keys,
    optional_keys=[],
    check_reverse=False,
    raise_if_wrong=True,
):
    check_1 = False
    check_2 = False

    for key in required_keys:
        check_1 = check_element_in_iterable(
            dict, key, "key", "dict", raise_if_wrong=raise_if_wrong
        )
        if not check_1:
            break
    if check_1:
        if check_reverse:
            allowed_keys = set(required_keys + optional_keys)
            for key in dict.keys():
                check_2 = check_element_in_iterable(
                    allowed_keys,
                    key,
                    "key",
                    "set of allowed keys",
                    reference=dict,
                    raise_if_wrong=raise_if_wrong,
                )
                if not check_2:
                    break
        else:
            check_2 = True
    return check_1 and check_2


def run_cmd_through_popen(
    cmd_to_run,
    logger,
    stdout_buffer_processor=None,
    stderr_buffer_processor=None,
):
    def read_out(process, out_type, logger, buffer_processor=None):
        def process_buffer(buffer, prev_buffer, buffer_processor, log_func):
            if buffer_processor is not None:
                buffer_processor(prev_buffer + buffer)
            log_func(buffer, logger)
            prev_buffer = buffer
            buffer = ""
            return buffer, prev_buffer

        buffer = ""
        prev_buffer = ""
        if out_type == "stdout":
            out = process.stdout
            log_func = log_or_print
        else:
            assert out_type == "stderr"
            out = process.stderr
            log_func = error_or_print

        while True:
            output = out.readline()
            if output == "" and process.poll() is not None:
                break

            buffer += output

            if output == "\n" or len(buffer) > MAX_BUFFER_SIZE:
                buffer, prev_buffer = process_buffer(
                    buffer, prev_buffer, buffer_processor, log_func
                )

        if buffer != "":
            process_buffer(buffer, prev_buffer, buffer_processor, log_func)

    process = subprocess.Popen(
        cmd_to_run,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    log_or_print(f"Process started by runner has id: {process.pid}", logger)

    stdout_thread = threading.Thread(
        target=read_out,
        args=(process, "stdout", logger, stdout_buffer_processor),
    )
    stderr_thread = threading.Thread(
        target=read_out,
        args=(process, "stderr", logger, stderr_buffer_processor),
    )

    stdout_thread.start()
    stderr_thread.start()

    stdout_thread.join()
    stderr_thread.join()

    process.wait()

    if process.returncode != 0:
        raise Exception(
            f"Process failed with return code: {process.returncode}. "
            f"Check stderr for details"
        )


def runcmd(cmd, verbose=False, logger=None):
    try:
        cmd_output = subprocess.check_output(
            cmd, stderr=subprocess.STDOUT, shell=True
        )
        if verbose:
            msg = cmd_output.decode("utf-8", errors="ignore")
            if msg:
                if logger:
                    logger.log(msg)
                else:
                    print(msg)
    except subprocess.CalledProcessError as e:
        raise Exception(e.output.decode("utf-8", errors="ignore"))


# def compute_dicts_diff(dict1, dict2, ignore_order=True):
#     ddiff = DeepDiff(dict1, dict2, ignore_order=ignore_order)
#     return ddiff


# def randomly_subsample_indices_uniformly(total_samples, num_to_subsample):


# def deterministically_subsample_indices_uniformly(
#     total_samples, num_to_subsample
# ):


# def get_device(use_gpu, idx=0):


# def get_model_device(model):


def get_project_root_path():
    if not PROJECT_ROOT_ENV_NAME in os.environ:
        raise Exception(
            f"STAI-tuned expects project root path "
            f'in variable "{PROJECT_ROOT_ENV_NAME}"'
        )
    return os.environ[PROJECT_ROOT_ENV_NAME]


def get_stuned_root_path():
    return os.path.abspath(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )
    )


def make_unique_run_name(hashed_config_diff):
    return "{}---{}---{}".format(
        get_current_time(), hashed_config_diff, os.getpid()
    ).replace(" ", "_")


def get_current_run_folder(experiment_name, hashed_config_diff):
    return os.path.join(
        get_project_root_path(),
        DEFAULT_EXPERIMENTS_FOLDER,
        experiment_name,
        make_unique_run_name(hashed_config_diff),
    )


def get_hash(input_object, hash_size=DEFAULT_HASH_SIZE):
    h = get_hasher("blake2b", hash_size=hash_size)
    h.update(input_object.__repr__().encode())
    return h.hexdigest()


def get_value_from_config(file_path, value_name):
    with open(file_path, "r") as f:
        for line in f.readlines():
            line_elements = line.split()
            if len(line_elements) == 0:
                continue
            if value_name == line_elements[0]:
                if len(line_elements) < 2:
                    raise Exception(
                        'Line "{}" does not have value'
                        ' for "{}".'.format(line, value_name)
                    )
                return line_elements[1]
    raise Exception(
        'File "{}" does not contain' ' "{}".'.format(file_path, value_name)
    )


def log_or_print(msg, logger=None, auto_newline=False):
    if logger:
        logger.log(msg, auto_newline=auto_newline)
    else:
        print(msg)


def error_or_print(msg, logger=None, auto_newline=False):
    if logger:
        logger.error(msg, auto_newline=auto_newline)
    else:
        print(msg, file=sys.stderr, flush=True)


# def read_checkpoint(checkpoint_path, map_location=None):


# def save_checkpoint(
#     checkpoint, checkpoint_folder, checkpoint_name=None, logger=None
# ):


def prepare_for_pickling(obj):
    if hasattr(obj, "_prepare_for_pickling"):
        obj._prepare_for_pickling()
    if hasattr(obj, "_prepare_for_pickling_external"):
        obj._prepare_for_pickling_external(obj)


def prepare_for_unpickling(obj):
    if hasattr(obj, "_prepare_for_unpickling"):
        obj._prepare_for_unpickling()
    if hasattr(obj, "_prepare_for_unpickling_external"):
        obj._prepare_for_unpickling_external(obj)


def make_checkpoint_name(checkpoint):
    return "checkpoint-epoch_{}.pkl".format(
        checkpoint["current_epoch"] + 1,
    )


def get_leaves_of_nested_dict(
    nested_dict,
    nested_key_prefix=[],
    include_values=False,
    allow_empty_dict=False,
):
    result = []
    if len(nested_dict) == 0:
        if allow_empty_dict:
            return result
        else:
            raise ValueError("Nested dict is empty.")
    for key, value in nested_dict.items():
        current_prefix = nested_key_prefix + [key]
        if isinstance(value, dict):
            result.extend(
                get_leaves_of_nested_dict(
                    value,
                    nested_key_prefix=current_prefix,
                    include_values=include_values,
                    allow_empty_dict=allow_empty_dict,
                )
            )
        else:
            if include_values:
                result.append((current_prefix, value))
            else:
                result.append(current_prefix)

    return result


def update_dict_by_nested_key(
    input_dict, nested_key_as_list, new_value, to_create_new_elements=False
):
    apply_func_to_dict_by_nested_key(
        input_dict,
        nested_key_as_list,
        lambda x: new_value,
        to_create_new_elements,
    )


def apply_func_to_dict_by_nested_key(
    input_dict, nested_key_as_list, func, to_create_new_elements=False
):
    if not isinstance(input_dict, dict):
        raise Exception(
            '"{}" is expected to be a dict '
            "containing the following nested dicts: \n{}".format(
                input_dict, nested_key_as_list[:-1]
            )
        )
    if not isinstance(nested_key_as_list, list):
        raise Exception(
            '"{}" is expected '
            "to be a list of nested keys for dict: \n{}".format(
                nested_key_as_list, input_dict
            )
        )
    if len(nested_key_as_list) == 0:
        raise Exception("Empty nested key was given for dict update.")
    else:
        current_key = nested_key_as_list[0]
        is_leaf = len(nested_key_as_list) == 1

        if not current_key in input_dict:
            if to_create_new_elements:
                if is_leaf:
                    input_dict[current_key] = None
                else:
                    input_dict[current_key] = {}
            else:
                raise Exception(
                    "During recursive dict update {} "
                    "was not found in {}".format(current_key, input_dict)
                )

        if is_leaf:
            input_dict[current_key] = func(input_dict[current_key])
        else:
            new_subdict = input_dict[current_key]
            apply_func_to_dict_by_nested_key(
                new_subdict,
                nested_key_as_list[1:],
                func,
                to_create_new_elements,
            )
            input_dict[current_key] = new_subdict


def extract_profiler_results(prof):
    return prof.key_averages(group_by_stack_n=PROFILER_GROUP_BY_STACK_N).table(
        sort_by="self_cuda_memory_usage", row_limit=PROFILER_OUTPUT_ROW_LIMIT
    )


def check_equal_shape(tensors_list):
    shape = None
    for tensor in tensors_list:
        if shape:
            assert tensor.shape == shape
        else:
            shape = tensor.shape


def move_folder_contents(src_folder, dst_folder):
    for file_or_folder in os.listdir(src_folder):
        dst_path = os.path.join(dst_folder, file_or_folder)
        assert not os.path.exists(dst_path)
        os.rename(os.path.join(src_folder, file_or_folder), dst_path)


def remove_all_but_subdirs(src_folder, objects_to_keep):
    for object_name in objects_to_keep:
        assert os.path.exists(os.path.join(src_folder, object_name))
    objects_to_keep = set(objects_to_keep)
    objects_in_folder_before = os.listdir(src_folder)
    for object_name in objects_in_folder_before:
        if not object_name in objects_to_keep:
            remove_file_or_folder(os.path.join(src_folder, object_name))
    assert len(objects_to_keep) == len(os.listdir(src_folder))


def remove_file_or_folder(file_or_folder):
    if os.path.isfile(file_or_folder):
        os.remove(file_or_folder)
    elif os.path.isdir(file_or_folder):
        shutil.rmtree(file_or_folder)
    else:
        raise_unknown("file type", "", 'for object "{}"'.format(file_or_folder))


def is_nested_dict(input_dict):
    for value in input_dict.values():
        if isinstance(value, dict):
            return True
    return False


def ensure_separator_after_folder(folder_path):
    assert os.path.isdir(folder_path)
    if folder_path[-1] != os.path.sep:
        folder_path += os.path.sep
    return folder_path


def compute_file_hash(
    filename, chunksize=DEFAULT_FILE_CHUNK_SIZE, hash_type="md5"
):
    hasher = get_hasher(hash_type)
    with open(filename, "rb") as f:
        for byte_block in iter(lambda: f.read(chunksize), b""):
            hasher.update(byte_block)
    return hasher.hexdigest()


def get_hasher(hash_type, hash_size=DEFAULT_HASH_SIZE):
    if hash_type == "md5":
        return md5()
    elif hash_type == "blake2b":
        return blake2b(digest_size=hash_size)
    else:
        raise_unknown("hash type", hash_type, "getting hasher")


def get_hostname():
    return socket.gethostname()


def remove_filename_extension(filename, must_have_extension=True):
    if "." in filename:
        filename = filename[: filename.find(".")]
        assert "." not in filename
    elif must_have_extension:
        raise Exception(
            "Filename {} is expected to have extension".format(filename)
        )
    return filename


def range_for_each_group(num_groups, num_elements):
    assert num_elements >= num_groups

    indices_per_group = int(num_elements / num_groups)
    remainder = num_elements % num_groups

    return [
        (
            group_id * indices_per_group + (min(group_id, remainder)),
            (group_id + 1) * (indices_per_group)
            + (min(group_id, remainder - 1) + 1),
        )
        for group_id in range(num_groups)
    ]


def coefficients_for_bases(number, bases):
    combination = []
    prev_base = float("Inf")
    for base in bases:
        assert prev_base > base
        current_value = int(number / base)
        combination.append(current_value)
        number = number % base
        if len(combination) < len(bases):
            prev_base = base
        else:
            assert number == 0
    return combination


def error_callback(exception):
    raise Exception("".join(traceback.format_exception(exception)))


def deterministic_subset(input_set, num_to_subsample):
    assert num_to_subsample <= len(input_set)
    subsampled_idxs = np.linspace(
        0, len(input_set) - 1, num_to_subsample, dtype=np.int32
    )
    res = set()
    set_as_list = sorted(list(input_set))
    for i in subsampled_idxs:
        res.add(set_as_list[i])
    return res


def compute_proportion(proportion, total_number):
    return max(1, int(proportion * total_number))


def make_autogenerated_config_name(input_csv_path, row_number):
    return "[{}]_{}_autogenerated_config.yaml".format(
        row_number, get_hash(input_csv_path)
    )


def save_as_yaml(output_file_name, data):
    with open(output_file_name, "w") as outfile:
        yaml.dump(data, outfile, default_flow_style=False)


def write_into_csv_pd(
    file_path,
    row_number,  # starts with 1
    column_name,
    value,
    use_lock=True,
    allow_creating_file=False,
):
    assert row_number > 0, "Rows enumeration starts with 1."

    new_file = False

    row_number -= 1

    if not os.path.exists(file_path):
        if allow_creating_file:
            tmp_col_name = "tmp_col"
            new_file = True
            touch_file(file_path)
            print(tmp_col_name, file=open(file_path, "w"))
        else:
            raise FileNotFoundError(f"File {file_path} does not exist")

    lock = make_file_lock(file_path) if use_lock else NULL_CONTEXT

    with lock:
        df = pd.read_csv(file_path)

        if new_file:
            df = df.drop(columns=[tmp_col_name])

        num_rows = df.shape[0]
        if num_rows < row_number:
            num_empty_rows_to_append = row_number - num_rows

            empty_rows = pd.DataFrame(
                {
                    col: [pd.NA for _ in range(num_empty_rows_to_append)]
                    for col in df.columns
                }
            )

            df = pd.concat([df, empty_rows], ignore_index=True)

        df.at[row_number, column_name] = value

        df.to_csv(file_path, index=False)


def write_into_csv_with_column_names(
    file_path,
    row_number,
    column_name,
    value,
    delimiter=DELIMETER,
    quotechar=QUOTE_CHAR,
    quoting=csv.QUOTE_NONE,
    escapechar=ESCAPE_CHAR,
    doublequote=True,
    replace_nulls=False,
    append_row=False,
    use_lock=True,
):
    """
    Insert <value> into the intersection of row number <row_number>
    and column <column_name> of the csv file with path <file_path>.


    Args:

        file_path (str): path of csv file in filesystem.

        row_number (int): number of row in which <value> should be inserted.
            Rows numbering starts with 0. Row 0 is the row with column names.
            Therefore if <row_number> equals 0, column renaming will take place
            (but it is possible only for a non-empty file).
            For an empty file <row_number> should be 1,
            as a new column will be created anyway.

        column_name (str): column in which <value> should be inserted.
            If the csv file does not contain <column_name>,
            new column with the name <column_name> is created.
            When new column is created row <row_number> is filled with <value>
            other rows are filled with "EMPTY_CSV_TOKEN" if they exist.

        value (Any): value to insert into the csv file.
            It is converted to string before insertion.

        other args
    """

    tempfile = NamedTemporaryFile("w+t", newline="", delete=False)

    lock = make_file_lock(file_path) if use_lock else NULL_CONTEXT

    with lock:
        with open(file_path, "r", newline="") as csv_file, tempfile:
            reader = csv.reader(
                (
                    (x.replace("\0", "") for x in csv_file)
                    if replace_nulls
                    else csv_file
                ),
                delimiter=delimiter,
                quotechar=quotechar,
                quoting=quoting,
                escapechar=escapechar,
                doublequote=doublequote,
            )
            writer = csv.writer(
                tempfile,
                delimiter=delimiter,
                quotechar=quotechar,
                quoting=quoting,
                escapechar=escapechar,
                doublequote=doublequote,
            )

            appended_column = False
            value_inserted = False

            num_rows = count_rows_in_file(csv_file)
            num_cols = None

            pos_in_row = None

            if num_rows == 0:
                assert row_number == 1, (
                    "Can't insert into row number {} of empty file, "
                    "only row number 1 is possible."
                ).format(row_number)

                writer.writerow([column_name])
                append_row = True
                num_cols = 1
                num_rows += 1

            else:
                for current_row_number, row in enumerate(reader):
                    if current_row_number == 0:
                        if column_name in row:
                            pos_in_row = row.index(column_name)
                        else:
                            row.append(column_name)
                            appended_column = True
                            pos_in_row = len(row) - 1

                    if current_row_number == row_number:
                        assert pos_in_row is not None
                        if appended_column and row_number > 0:
                            row.append(value)
                        else:
                            assert len(row) > pos_in_row, (
                                "CSV's contents are inconsistent "
                                "with the number of columns "
                                "for the file {}".format(file_path)
                            )
                            row[pos_in_row] = value
                        value_inserted = True
                    elif appended_column and current_row_number > 0:
                        row.append(EMPTY_CSV_TOKEN)

                    writer.writerow(row)
                    num_cols = len(row)

            if append_row:
                assert num_cols is not None and num_cols > 0

                assert row_number == num_rows

                writer.writerow([value] + [EMPTY_CSV_TOKEN] * (num_cols - 1))
                value_inserted = True

        if not value_inserted:
            raise Exception(
                "CSV file {} has {} rows, while insertion "
                "into row {} was requested!".format(
                    file_path, num_rows, row_number
                )
            )

        shutil.move(tempfile.name, file_path)


def count_rows_in_file(file):
    rowcount = 0

    for _ in file:
        rowcount += 1

    file.seek(0)

    return rowcount


def remove_elements_from_the_end(sequence, element_to_remove):
    assert len(sequence)

    end_pos = len(sequence) - 1

    while end_pos >= 0 and sequence[end_pos] == element_to_remove:
        end_pos -= 1

    return sequence[: end_pos + 1]


def itself_and_lower_upper_case(word):
    return (word, word.lower(), word.upper())


def decode_strings_in_dict(
    input_dict, list_separators, list_start_symbol, list_end_symbol
):
    for key, value in input_dict.items():
        if isinstance(value, str):
            if value == "":
                continue

            value = decode_val_from_str(
                value, list_separators, list_start_symbol, list_end_symbol
            )

            input_dict[key] = value


def decode_val_from_str(
    value,
    list_separators=[" ", ", ", ","],
    list_start_symbol="[",
    list_end_symbol="]",
):
    if isinstance(value, str):
        value = value.strip()

    if str_is_number(value):
        value = parse_float_or_int_from_string(value)

    elif len(value) > 1 and (
        value[0] == list_start_symbol or value[-1] == list_end_symbol
    ):
        assert (
            value[0] == list_start_symbol and value[-1] == list_end_symbol
        ), f"Possibly incomplete list expression: {value}"

        value = parse_list_from_string(
            value,
            list_separators=list_separators,
            list_start_symbol=list_start_symbol,
            list_end_symbol=list_end_symbol,
        )

    elif value in itself_and_lower_upper_case(
        "None"
    ) or value in itself_and_lower_upper_case("Null"):
        value = None

    elif value in itself_and_lower_upper_case("False"):
        value = False

    elif value in itself_and_lower_upper_case("True"):
        value = True

    return value


def replace_many_by_one(input_string, items_to_replace, value_to_insert):
    # TODO(Alex | 25.02.2023) do in O(n) with regex
    for item_to_replace in items_to_replace:
        if item_to_replace == value_to_insert:
            continue

        input_string = input_string.replace(item_to_replace, value_to_insert)

    return input_string


def str_is_number(input_str):
    if len(input_str) == 0:
        return False

    exponential = False
    has_floating_point = False
    for i in range(len(input_str)):
        if input_str[i].isdigit():
            continue
        if input_str[i] == "-":
            if i == 0:
                continue
            elif exponential and input_str[i - 1] in EXPONENTIAL_SYMBOLS:
                continue
        if (
            input_str[i] == "+"
            and exponential
            and input_str[i - 1] in EXPONENTIAL_SYMBOLS
        ):
            continue
        if input_str[i] in EXPONENTIAL_SYMBOLS and not exponential:
            exponential = True
            continue
        if input_str[i] == FLOATING_POINT and not has_floating_point:
            has_floating_point = True
            continue
        return False

    if exponential and not input_str[-1].isdigit():
        return False

    return True


def parse_float_or_int_from_string(value_as_str):
    if FLOATING_POINT in value_as_str or any(
        [exp in value_as_str for exp in EXPONENTIAL_SYMBOLS]
    ):
        return float(value_as_str)
    else:
        return int(value_as_str)


def escape_all_chars_in_string(input_string, escapechar=ESCAPE_CHAR):
    return escapechar + escapechar.join(list(input_string))


def parse_list_from_string(
    value_as_str,
    list_separators,
    list_start_symbol=LIST_START_SYMBOL,
    list_end_symbol=LIST_END_SYMBOL,
):
    assert len(list_separators)
    assert len(value_as_str) > 1
    assert (
        value_as_str[0] == list_start_symbol
        and value_as_str[-1] == list_end_symbol
    )

    if len(value_as_str) == 2:
        return []
    else:
        value_as_str = value_as_str[1:-1]

        replace_many_by_one(value_as_str, list_separators, list_separators[0])

        value_as_str = re.sub(
            f"({escape_all_chars_in_string(list_separators[0])})+",
            list_separators[0],
            value_as_str,
        )

        result_list = value_as_str.split(list_separators[0])

        for i in range(len(result_list)):
            result_list[i] = decode_val_from_str(
                result_list[i],
                list_separators,
                list_start_symbol,
                list_end_symbol,
            )

        return result_list


def read_csv_as_dict(
    csv_path,
    delimeter=DELIMETER,
    quotechar=QUOTE_CHAR,
    quoting=csv.QUOTE_NONE,
    escapechar=ESCAPE_CHAR,
    doublequote=True,
):
    result = {}

    with open(csv_path, newline="") as input_csv:
        csv_reader = csv.DictReader(
            input_csv,
            delimiter=delimeter,
            quotechar=quotechar,
            quoting=quoting,
            escapechar=escapechar,
            doublequote=doublequote,
        )

        result[0] = {}

        check_duplicates(csv_reader.fieldnames)

        for fieldname in csv_reader.fieldnames:
            result[0][fieldname] = fieldname

        for csv_row_number, csv_row in enumerate(csv_reader):
            result[csv_row_number + 1] = csv_row

    return result


def read_csv_as_dict_pd(csv_path):
    result = pd.read_csv(csv_path)
    cols_row = pd.DataFrame({col: [col] for col in result.columns})
    result = pd.concat([cols_row, result]).reset_index().transpose()
    result = result.drop("index").to_dict(orient="dict")

    return result


def normalize_string_path(path, current_dir):
    if current_dir is None:
        current_dir = get_project_root_path()
    path = os.path.expanduser(path)
    if path[0] == ".":
        path = os.path.join(current_dir, path)
    env_vars = ENV_VAR_RE.findall(path)
    for env_var in env_vars:
        assert (
            env_var in os.environ
        ), f"Environment variable {env_var} is not set."
        path = path.replace(f"<${env_var}>", os.environ[env_var])

    return os.path.abspath(path)


def normalize_path(path, current_dir=None):
    if path is None:
        return None
    if isinstance(path, str):
        assert path
        return normalize_string_path(path, current_dir)
    elif isinstance(path, list):
        assert path
        return [normalize_string_path(p, current_dir) for p in path]
    else:
        raise ValueError(f"Path must be either str or list, got {type(path)}")


def read_json(json_path):
    with open(json_path, "r") as f:
        json_contents = json.load(f)
        return json_contents


def dicts_with_non_intersecting_keys(dict_one, dict_two):
    return len(set(dict_one.keys()).intersection(set(dict_two.keys()))) == 0


def is_number(x):
    return str_is_number(str(x))


# def assert_two_values_are_close(value_1, value_2, **isclose_kwargs):


def bootstrap_by_key_subname(input_dict, subname_to_bootstrap):
    """
    Recursively lift dict entries which contain <subname_to_bootstrap>
    in their key on the upper level from leaves to root.

    Example:
        <subname_to_bootstrap> = "subkey"
        input_dict = {
            "a": 1,
            "b": {
                "csubkeyd": {
                    "e": 2,
                    "gsubkeyh": 3
                },
                "f": 4
            }
        }
        result = {
            "a": 1,
            "b": 3
        }
    """
    new_key_values = []
    for key, value in input_dict.items():
        if isinstance(value, dict):
            bootstrap_by_key_subname(value, subname_to_bootstrap)
            key_of_interest = find_by_subkey(value.keys(), subname_to_bootstrap)
            if key_of_interest is not None:
                new_key_values.append((key, value[key_of_interest]))
    for key, new_value in new_key_values:
        input_dict[key] = new_value


def find_by_subkey(
    iterable, subkey, assert_found=False, only_first_occurence=True
):
    result = []
    for key in iterable:
        if isinstance(key, str) and subkey in key:
            if only_first_occurence:
                return key
            else:
                result.append(key)

    if len(result) > 0:
        return result

    if assert_found:
        assert False, "Key with subkey {} wasn't found in {}.".format(
            subkey, iterable
        )

    return None


def get_system_root_path():
    return os.path.abspath(os.sep)


def prepare_factory_without_args(func, **kwargs):
    def factory_without_args():
        return func(**kwargs)

    return factory_without_args


def raise_func(logger):
    error_or_print(MAX_RETRIES_ERROR_MSG, logger)
    raise


def retrier_factory(
    logger=None,
    final_func=raise_func,
    max_retries=DEFAULT_NUM_ATTEMTPS,
    sleep_time=DEFAULT_SLEEP_TIME,
    infer_logger_from_args=None,
):
    assert (
        logger != "auto"
        and infer_logger_from_args is None
        or logger == "auto"
        and infer_logger_from_args is not None
    ), 'Provide "infer_logger_from_args" iff "logger == auto"'

    def retrier(func):
        # without this line logger is not seen in wrapped_func
        logger_in_retrier = logger

        def wrapped_func(*args, **kwargs):
            logger = logger_in_retrier

            if logger == "auto":
                logger = infer_logger_from_args(*args, **kwargs)

            num_attempts = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except:
                    if num_attempts >= max_retries:
                        return final_func(logger)
                    num_attempts += 1
                    time.sleep(sleep_time)
                    retry_print = None
                    if logger is not None and hasattr(logger, "retry_print"):
                        retry_print = logger.retry_print
                        logger.retry_print = False
                    retrying_msg = "{}\nRetrying {}: {}/{}.\n\n".format(
                        traceback.format_exc(),
                        func.__name__,
                        num_attempts,
                        max_retries,
                    )
                    try:
                        error_or_print(retrying_msg, logger)
                    except:
                        print(retrying_msg)
                    if retry_print is not None:
                        logger.retry_print = retry_print

        return wrapped_func

    return retrier


# from: https://stackoverflow.com/questions/8230315/how-to-json-serialize-sets
class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            from deepdiff import DeepDiff, model as dd_model
        except ImportError:
            raise ImportError(
                "Please install deepdiff to use pretty_json: "
                "pip install deepdiff"
            )
        if isinstance(obj, (set, dd_model.PrettyOrderedSet)):
            return list(obj)
        return json.JSONEncoder.default(self, obj)


# from: https://www.tensorflow.org/tensorboard/text_summaries
def pretty_json(hp, cls=SetEncoder, default=str):
    json_hp = json.dumps(
        hp, indent=DEFAULT_INDENT_IN_JSON, cls=cls, default=default
    )
    return "".join("\t" + line for line in json_hp.splitlines(True))


def touch_file(file_path):
    open(file_path, "a").close()
    return file_path


# def cat_or_assign(accumulating_tensor, new_tensor):


def kill_processes(processes_to_kill, logger=None):
    for process_to_kill in processes_to_kill:
        try:
            os.kill(process_to_kill, signal.SIGTERM)
        except Exception:
            error_or_print(traceback.format_exc(), logger)


# def read_old_checkpoint(checkpoint_path, map_location=None):


# def read_model_from_old_checkpoint(path):


def make_file_lock(file_name):
    return FileLock("{}.lock".format(file_name))


def check_duplicates(input_list):
    counter_dict = dict(Counter(input_list))
    duplicate_dict = {
        key: value for key, value in counter_dict.items() if value > 1
    }
    if len(duplicate_dict) > 0:
        raise Exception(
            f"Duplicates in:\n{input_list}\n\nDuplicates:\n{duplicate_dict}"
        )


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key, value in self.items():
            if isinstance(value, dict):
                self[key] = AttrDict(value)

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(f"'AttrDict' object has no attribute '{item}'")

    def __setattr__(self, key, value):
        self[key] = value

    def __deepcopy__(self, memo):
        # Create a deepcopy of the object and its nested elements
        copied = AttrDict()
        for key, value in self.items():
            copied[key] = copy.deepcopy(value, memo)
        return copied


def has_nested_attr(object, nested_attr):
    assert len(nested_attr) > 0
    if isinstance(object, dict):
        object = AttrDict(object)
    if len(nested_attr) == 1:
        return hasattr(object, nested_attr[0])
    else:
        return hasattr(object, nested_attr[0]) and has_nested_attr(
            getattr(object, nested_attr[0]), nested_attr[1:]
        )


def get_nested_attr(object, nested_attr):
    assert len(nested_attr) > 0
    if isinstance(object, dict):
        object = AttrDict(object)
    if len(nested_attr) == 1:
        return getattr(object, nested_attr[0])
    else:
        return get_nested_attr(getattr(object, nested_attr[0]), nested_attr[1:])


def set_nested_attr(object, nested_attr, value):
    assert len(nested_attr) > 0
    if isinstance(object, dict):
        update_dict_by_nested_key(object, nested_attr, value)
    else:
        if len(nested_attr) == 1:
            return setattr(object, nested_attr[0], value)
        else:
            set_nested_attr(
                getattr(object, nested_attr[0]), nested_attr[1:], value
            )


def write_csv_dict_to_csv(dict_from_csv, csv_file, **kwargs):
    if os.path.exists(csv_file):
        remove_file_or_folder(csv_file)

    touch_file(csv_file)

    for row_number, row_as_dict in dict_from_csv.items():
        if row_number == 0:
            continue
        for i, (column_name, value) in enumerate(row_as_dict.items()):
            write_into_csv_with_column_names(
                csv_file,
                row_number,
                column_name,
                value,
                append_row=(i == 0),
                **kwargs,
            )


def write_csv_dict_to_csv_pd(dict_from_csv, csv_file):
    df = pd.DataFrame.from_dict(dict_from_csv, orient="index")
    df = df.iloc[1:]
    df.to_csv(csv_file, index=False)


def expand_csv(
    csv_to_expand,
    expanded_csv,
    expansion_start_symbol="{",
    expansion_end_symbol="}",
    expansion_delimeter=" | ",
    range_start_symbol="<",
    range_end_symbol=">",
    range_delimeter=" ",
):
    def expand_row(
        row_as_dict,
        expansion_start_symbol,
        expansion_end_symbol,
        expansion_delimeter,
        range_start_symbol,
        range_end_symbol,
        range_delimeter,
    ):
        def build_range(range_as_str, range_delimeter):
            range_as_str_split = range_as_str.split(range_delimeter)
            assert len(range_as_str_split) == 4
            for i in range(len(range_as_str_split)):
                range_as_str_split[i] = decode_val_from_str(
                    range_as_str_split[i]
                )

            start = range_as_str_split[0]
            end = range_as_str_split[1]
            step = range_as_str_split[2]
            log_scale = range_as_str_split[3]
            result = []

            assert (
                step > 1 if log_scale else step > 0
            ), "Range should be increasing"

            while start < end:
                result.append(start)

                if log_scale:
                    start *= step
                else:
                    start += step

            return result

        keys = list(row_as_dict.keys())
        for key in keys:
            value = row_as_dict[key]
            if isinstance(value, str):
                value = value.strip()
            if (
                isinstance(value, str)
                and len(value) >= 2
                and value[0] == expansion_start_symbol
                and value[-1] == expansion_end_symbol
            ):
                if (
                    len(value) >= 4
                    and value[1] == range_start_symbol
                    and value[-2] == range_end_symbol
                ):
                    assert len(value) > 4, "Empty range expression"
                    assert (
                        range_delimeter in value
                    ), f"Range expression without range delimeter {value}"
                    value = (
                        expansion_start_symbol
                        + expansion_delimeter.join(
                            str(el)
                            for el in build_range(value[2:-2], range_delimeter)
                        )
                        + expansion_end_symbol
                    )

                row_as_dict[key] = parse_list_from_string(
                    value,
                    [expansion_delimeter],
                    list_start_symbol=expansion_start_symbol,
                    list_end_symbol=expansion_end_symbol,
                )
            else:
                row_as_dict[key] = [value]

        cross_product = itertools.product(*[row_as_dict[key] for key in keys])

        result = []
        for values in cross_product:
            result.append({key: value for key, value in zip(keys, values)})

        return result

    dict_to_expand = read_csv_as_dict(csv_to_expand)
    expanded_dict = {}
    final_row_id = 0

    for row_as_dict in dict_to_expand.values():
        expanded_rows = expand_row(
            row_as_dict,
            expansion_start_symbol=expansion_start_symbol,
            expansion_end_symbol=expansion_end_symbol,
            expansion_delimeter=expansion_delimeter,
            range_start_symbol=range_start_symbol,
            range_end_symbol=range_end_symbol,
            range_delimeter=range_delimeter,
        )
        for row in expanded_rows:
            expanded_dict[final_row_id] = row
            final_row_id += 1

    write_csv_dict_to_csv(expanded_dict, expanded_csv)


def instantiate_from_config(config, object_key_in_config, make_func, logger):
    object_config = config.get(object_key_in_config)
    if object_config is None:
        return None
    else:
        return make_func(object_config, logger)


# class TimeStampEventHandler(FileSystemEventHandler):
#     def __init__(self):
#         super(TimeStampEventHandler, self).__init__()
#         self.update_time()

#     def on_any_event(self, event):
#         self.update_time()

#     def update_time(self):
#         self.last_change_time = get_current_time()

#     def has_events(self, delta):
#         time_since_last_change = (
#             get_current_time() - self.last_change_time
#         ).total_seconds()
#         if time_since_last_change <= delta:
#             return True
#         else:
#             return False


# def folder_still_has_updates(path, delta, max_time, check_time=None):
#     """
#     Check every <check_time> seconds whether <path> had any updates (events).
#     Observe the <path> for at most <max_time>.
#     If there were no updates for <delta> seconds return True, otherwise return
#     False. If watchdog observer failed to start return None.
#     """

#     if check_time is None:
#         check_time = delta

#     n = max(1, int(max_time / check_time))
#     i = 0
#     event_handler = TimeStampEventHandler()
#     observer = Observer()
#     observer.schedule(event_handler, path, recursive=True)

#     try:
#         observer.start()
#     except:
#         return None

#     has_events_bool = event_handler.has_events(delta)
#     while has_events_bool and i < n:
#         time.sleep(check_time)
#         i += 1
#         has_events_bool = event_handler.has_events(delta)

#     observer.stop()
#     observer.join()

#     return has_events_bool


def as_str_for_csv(value, chars_to_remove=[]):
    if value is None:
        value = "None"
    value = str(value)

    for char in chars_to_remove:
        value = value.replace(char, "")

    return value


def check_consistency(
    first, second, first_consistent_group, second_consistent_group
):
    def make_msg(
        first, first_consistent_group, second, second_consistent_group
    ):
        return ("{} is from {}, therefore {} " "should be from {}.").format(
            first, first_consistent_group, second, second_consistent_group
        )

    try:
        if first in first_consistent_group:
            exception_msg = make_msg(
                first, first_consistent_group, second, second_consistent_group
            )
            assert second in second_consistent_group
        if second in second_consistent_group:
            exception_msg = make_msg(
                second, second_consistent_group, first, first_consistent_group
            )
            assert first in first_consistent_group
    except AssertionError as e:
        raise Exception(exception_msg)


# def aggregate_tensors_by_func(input_list, func=torch.mean):


def func_for_dim(func, dim):
    def inner_func(*args, **kwargs):
        return func(*args, **kwargs, dim=dim)

    return inner_func


def parse_name_and_number(name_and_number, separator=NAME_NUMBER_SEPARATOR):
    assert separator in name_and_number
    split = name_and_number.split(separator)
    assert len(split) == 2
    assert is_number(split[-1])
    return split[0], parse_float_or_int_from_string(split[-1])


# def show_images(images, label_lists=None):
#     def remove_ticks_and_labels(subplot):
#         subplot.axes.xaxis.set_ticklabels([])
#         subplot.axes.yaxis.set_ticklabels([])
#         subplot.axes.xaxis.set_visible(False)
#         subplot.axes.yaxis.set_visible(False)

#     def get_row_cols(n):
#         n_rows = int(np.sqrt(n))
#         n_cols = int(n / n_rows)
#         if n % n_rows != 0:
#             n_cols += 1
#         return n_rows, n_cols

#     n = len(images)
#     assert n > 0
#     if label_lists is not None:
#         for label_list in label_lists.values():
#             assert len(label_list) == n

#     n_rows, n_cols = get_row_cols(n)

#     cmap = get_cmap(images[0])
#     fig = plt.figure(figsize=(n_cols * PLT_COL_SIZE, n_rows * PLT_ROW_SIZE))
#     for i in range(n):
#         subplot = fig.add_subplot(n_rows, n_cols, i + 1)
#         title = f"n{i}"
#         if label_lists is not None:
#             for label_name, label_list in label_lists.items():
#                 title += f'\n{label_name}="{label_list[i]}"'
#         subplot.title.set_text(title)
#         remove_ticks_and_labels(subplot)

#         imshow(subplot, images[i], cmap=cmap)

#     plt.tight_layout()
#     plt.show()


# def imshow(plot, image, cmap=None, color_dim_first=True):
#     image = image.squeeze()
#     num_image_dims = len(image.shape)
#     if cmap is None:
#         cmap = get_cmap(image)
#     assert num_image_dims == 2 or num_image_dims == 3
#     if num_image_dims == 3 and color_dim_first:
#         image = np.transpose(image, (1, 2, 0))
#     plot.imshow(image, cmap=cmap)


# def get_cmap(image):
#     cmap = "viridis"
#     squeezed_shape = image.squeeze().shape
#     if len(squeezed_shape) == 2:
#         cmap = "gray"
#     return cmap


# def compute_tensor_cumsums(tensor):


# def compute_unique_tensor_value(tensor):


def prune_list(l, value):
    return list(filter((value).__ne__, l))


def get_with_assert(container, key, error_msg=None):
    if isinstance(key, list):
        assert len(key) > 0
        next_key = key[0]
        rest_key = key[1:]
        next_container = get_with_assert(container, next_key, error_msg)
        if len(rest_key) == 0:
            return next_container
        else:
            return get_with_assert(next_container, rest_key, error_msg)
    else:
        key_in_container = key in container

        if not key_in_container:
            if error_msg is None:
                error_msg = f'Key "{key}" not in container: {container}'

            raise Exception(error_msg)

        return container[key]


def properties_diff(first_object, second_object, only_local=True):
    if only_local:
        first_object_properties = first_object.__dict__.keys()
        second_object_properties = second_object.__dict__.keys()
    else:
        first_object_properties = dir(first_object)
        second_object_properties = dir(second_object)
    return set(first_object_properties).difference(
        set(second_object_properties)
    )


def get_even_from_wrapped(giver, wrappable_as_property, property_to_get):
    if hasattr(giver, property_to_get):
        return getattr(giver, property_to_get)
    elif hasattr(giver, wrappable_as_property):
        return get_even_from_wrapped(
            getattr(giver, wrappable_as_property),
            wrappable_as_property,
            property_to_get,
        )
    return None


def add_custom_properties(giver, taker, only_local=True):
    custom_properties = properties_diff(giver, taker, only_local=only_local)
    for custom_property in custom_properties:
        setattr(taker, custom_property, getattr(giver, custom_property))


def invert_dict(d, none_to_string=False):
    res = {}
    for key, container in d.items():
        assert isinstance(container, Iterable)
        for value in container:
            if none_to_string and value is None:
                value = "None"
            assert value not in res, f"Dict is not invertible: {d}"
            res[value] = key
    return res


def load_from_pickle(path):
    return pickle.load(open(path, "rb"))


def extract_list_from_huge_string(huge_string, separator="\n"):
    assert isinstance(huge_string, str)
    split = huge_string.split(separator)
    res = []
    for el in split:
        el = el.strip()
        if el != "":
            res.append(el)
    return res


def apply_pairwise(iterable, func):
    if len(iterable) == 1:
        return iterable

    pairs = itertools.combinations(iterable, 2)
    res = []
    for a, b in pairs:
        res.append(func(a, b))
    return res


# def download_file(file_path, download_url):
#     if not os.path.exists(file_path):
#         os.makedirs(os.path.dirname(file_path), exist_ok=True)
#         if "google" in download_url:
#             download_type = "gdrive"
#         else:
#             download_type = "wget"

#         if download_type == "wget":
#             run_cmd_through_popen(
#                 f"wget {download_url} -O {file_path}", logger=None
#             )
#         else:
#             assert download_type == "gdrive"
#             assert "uc?id=" in download_url, (
#                 "When using gdown, url should be of form: "
#                 "https://drive.google.com/uc?id=<file_id>"
#             )

#             gdown.download(
#                 download_url,
#                 file_path,
#                 quiet=False,
#                 use_cookies=False,
#                 fuzzy=True,
#             )


def extract_tar_to_folder(tar_path, folder, verbose=False):
    is_gzip = tar_path.endswith(".tar.gz")
    tar_flags = "-x"
    if verbose:
        tar_flags += "v"
    if is_gzip:
        tar_flags += "z"
    tar_flags += "f"
    run_cmd_through_popen(
        f"tar {tar_flags} {tar_path} -C {folder}", logger=None
    )


def create_tar_from_folder(tar_path, folder, verbose=False):
    assert tar_path.endswith(".tar.gz")
    tar_flags = "-hcz"
    if verbose:
        tar_flags += "v"
    tar_flags += "f"
    run_cmd_through_popen(f"tar {tar_flags} {tar_path} {folder}", logger=None)


def get_filename_from_url(url):
    filename = None

    # Method 1: Try to get from Content-Disposition header
    try:
        response = requests.head(url)
        if "Content-Disposition" in response.headers:
            # Look for filename in header
            content_disposition = response.headers["Content-Disposition"]
            if "filename=" in content_disposition:
                filename = content_disposition.split("filename=")[1].strip(
                    "\"'"
                )
    except:
        pass

    # Method 2: Parse from URL path
    if filename is None:
        filename = os.path.basename(urlparse(url).path)

    return filename


# def download_and_extract_tar(
#     parent_folder, download_url, name=None, extension=None
# ):
#     if name is None:
#         cur_time = str(get_current_time()).replace(" ", "_")
#         name = f"tmp_tar_{cur_time}"
#     if extension is None:
#         original_filename = get_filename_from_url(download_url)
#         if original_filename is not None and "." in original_filename:
#             before, dot, after = original_filename.partition(".")
#             extension = dot + after
#         else:
#             extension = ".tar.gz"
#     downloaded_tar = os.path.join(parent_folder, f"{name}{extension}")
#     download_file(downloaded_tar, download_url)
#     extract_tar_to_folder(downloaded_tar, parent_folder)
#     remove_file_or_folder(downloaded_tar)


def optionally_make_parent_dir(path, call_dirname=True):
    if call_dirname:
        base_dir = os.path.dirname(path)
    else:
        base_dir = path
    if base_dir != "":
        os.makedirs(base_dir, exist_ok=True)
