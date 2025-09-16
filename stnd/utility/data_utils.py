import pickle
import os
import gc
import warnings
import traceback
from collections import UserDict
import sys

FINGERPRINT_ATTR = "object_fingerprint"


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from stnd.utility.utils import (
    get_project_root_path,
    get_hash,
    log_or_print,
    error_or_print,
    prepare_for_pickling,
    load_from_pickle,
)

sys.path.pop(0)


def make_default_cache_path():
    return os.path.join(get_project_root_path(), "cache")


def default_pickle_load(path):
    return load_from_pickle(path)


def default_pickle_save(obj, path):
    prepare_for_pickling(obj)
    with open(path, "wb") as f:
        pickle.dump(obj, f)


def make_or_load_from_cache(
    object_name,
    object_config,
    make_func,
    load_func=default_pickle_load,
    save_func=default_pickle_save,
    cache_path=None,
    forward_cache_path=False,
    logger=None,
    unique_hash=None,
    verbose=False,
    check_gc=False,
):
    def update_object_fingerprint_attr(result, object_fingerprint):
        if isinstance(result, dict):
            result = UserDict(result)

        setattr(result, FINGERPRINT_ATTR, object_fingerprint)
        return result

    if unique_hash is None:
        unique_hash = get_hash(object_config)

    if cache_path is None:
        cache_path = make_default_cache_path()

    object_fingerprint = "{}_{}".format(object_name, unique_hash)

    if check_gc:
        objects_with_the_same_fingerprint = extract_from_gc_by_attribute(
            FINGERPRINT_ATTR, object_fingerprint
        )

        if len(objects_with_the_same_fingerprint) > 0:
            if verbose:
                log_or_print(
                    "Reusing object from RAM with fingerprint {}".format(
                        object_fingerprint
                    ),
                    logger=logger,
                )
            return objects_with_the_same_fingerprint[0]

    if cache_path is None:
        cache_fullpath = None
    else:
        os.makedirs(cache_path, exist_ok=True)
        cache_fullpath = os.path.join(
            cache_path, "{}.pkl".format(object_fingerprint)
        )

    if cache_fullpath and os.path.exists(cache_fullpath):
        if verbose:
            log_or_print(
                "Loading cached {} from {}".format(object_name, cache_fullpath),
                logger=logger,
                auto_newline=True,
            )

        try:
            result = load_func(cache_fullpath)
            # TODO(Alex | 22.02.2023) Remove this once logger is global
            if hasattr(result, "logger"):
                result.logger = logger
            return result
        except:
            error_or_print(
                "Could not load object from {}\nReason:\n{}".format(
                    cache_fullpath, traceback.format_exc()
                ),
                logger=logger,
            )

    if forward_cache_path:
        result = make_func(object_config, cache_path=cache_path, logger=logger)
    else:
        result = make_func(object_config, logger=logger)

    if cache_fullpath:
        try:
            save_func(result, cache_fullpath)
            if verbose:
                log_or_print(
                    "Saved cached {} into {}".format(
                        object_name, cache_fullpath
                    ),
                    logger=logger,
                    auto_newline=True,
                )
        except OSError:
            error_or_print(
                "Could not save cached {} to {}. "
                "Reason: \n{} \nContinuing without saving it.".format(
                    object_name, cache_fullpath, traceback.format_exc()
                ),
                logger=logger,
                auto_newline=True,
            )

    if check_gc:
        result = update_object_fingerprint_attr(result, object_fingerprint)

    return result


def extract_from_gc_by_attribute(attribute_name, attribute_value):
    res = []

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        for obj in gc.get_objects():
            has_attribute = False

            try:
                has_attribute = hasattr(obj, attribute_name)
            except:
                continue

            if has_attribute and (
                getattr(obj, attribute_name) == attribute_value
            ):
                res.append(obj)

    return res
