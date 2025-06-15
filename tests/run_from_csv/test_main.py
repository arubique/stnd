import os
import tempfile
import shutil
import pytest
import yaml
import pandas as pd
import sys
import subprocess
import time
import numpy as np


# local imports
CUR_FOLDER = os.path.dirname(os.path.abspath(__file__))
STND_ROOT = os.path.dirname(os.path.dirname(CUR_FOLDER))
sys.path.insert(
    0,
    STND_ROOT,
)
from stnd.utility.utils import (
    optionally_make_parent_dir,
    run_cmd_through_popen,
)
from stnd.run_from_csv.__main__ import RUNNER_PLACEHOLDER

sys.path.pop(0)


UNIQUE_COLUMNS = ["run_folder", "walltime"]
TOTAL_ROWS = 3
MAX_SLEEPS = 100
SMALL_SLEEP_TIME = 1
SLEEP_TIME = 5
# SKIP_TESTS = True
SKIP_TESTS = False


CANONICAL_FOLDER = os.path.join(CUR_FOLDER, "canonical_files")
EXECUTABLES_FOLDER = os.path.join(CUR_FOLDER, "executables")
CONFIGS_FOLDER = os.path.join(CUR_FOLDER, "configs")


def create_test_csv(csv_path, config_path, cluster_type="slurm"):
    """Create a test CSV file with minimal required columns."""
    path_to_main = os.path.join(EXECUTABLES_FOLDER, "executable.py")
    path_to_runner_target = os.path.join(EXECUTABLES_FOLDER, "runner_target.py")
    if cluster_type == "slurm":
        data = {
            "path_to_default_config": [config_path] * TOTAL_ROWS,
            "path_to_main": [path_to_main] * TOTAL_ROWS,
            "whether_to_run": ["1", "0", "1"],
            "slurm:cpus-per-task": ["4"] * TOTAL_ROWS,
            "slurm:partition": ["a100"] * TOTAL_ROWS,
            "delta:logging/wandb/netrc_path": ["~/.netrc"] * TOTAL_ROWS,
            "delta:logging/use_wandb": ["FALSE"] * TOTAL_ROWS,
            "delta:initialization_type": ["zeros", "random", "ones"],
            "delta:image/color": ["red"] * TOTAL_ROWS,
        }
    elif cluster_type == "runner":
        data = {
            "path_to_default_config": [config_path],
            "path_to_main": [RUNNER_PLACEHOLDER],
            "whether_to_run": ["1"],
            "delta:exec_path": [path_to_runner_target],
            "delta:conda_env": ["None"],
            "delta:is_python": ["True"],
            "delta:two_dash_flags": ["[print_stdout]"],
            "delta:single_dash_flags": ["[p]"],
        }
    else:
        raise ValueError(f"Invalid cluster type: {cluster_type}")
    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False)


def create_test_config(config_path):
    """Create a test config file."""
    config = {
        "initialization_type": 1,
        "image": {"shape": [64, 64], "color": "red"},
        "params": {"random_seed": 42},
        "logging": {
            "gdrive_storage_folder": None,
            "use_wandb": True,
            "wandb": {"netrc_path": "~/.netrc"},
            "use_tb": False,
        },
        "use_hardcoded_config": False,
    }
    with open(config_path, "w") as f:
        yaml.dump(config, f)


@pytest.fixture
def test_env(request):
    """Set up test environment with temporary files."""
    with tempfile.TemporaryDirectory(prefix=CUR_FOLDER) as temp_dir:
        print(f"temp_dir for testing: {temp_dir}")

        # Create symlink to parent repo's .git directory so git commands work
        # git diff in logs will show that all the files are deleted
        parent_git_dir = os.path.join(
            os.path.dirname(os.path.dirname(CUR_FOLDER)), ".git"
        )
        os.symlink(parent_git_dir, os.path.join(temp_dir, ".git"))

        os.environ["PROJECT_ROOT_PROVIDED_FOR_STUNED"] = temp_dir
        # Create test files
        csv_path = os.path.join(temp_dir, "test.csv")
        csv_path_runner = os.path.join(temp_dir, "test_runner.csv")
        config_path = os.path.join(CONFIGS_FOLDER, "config.yaml")
        config_path_runner = os.path.join(CONFIGS_FOLDER, "runner_config.yaml")

        # optionally can create config inplace: create_test_config(config_path)
        create_test_csv(csv_path, config_path)
        create_test_csv(
            csv_path_runner, config_path_runner, cluster_type="runner"
        )

        # Create necessary directories
        os.makedirs(os.path.join(temp_dir, "experiment_configs"), exist_ok=True)
        os.makedirs(os.path.join(temp_dir, "tmp"), exist_ok=True)

        env_dict = {
            "temp_dir": temp_dir,
            "csv_path": csv_path,
            "csv_path_runner": csv_path_runner,
            "config_path": config_path,
        }

        yield env_dict
        # Register cleanup to run after all tests
        request.addfinalizer(lambda: cleanup_test_env(env_dict))


def get_python_binary():
    # on github everything is in the base env, but when debugging
    # we need to use the envs/stnd_env env
    conda_env = os.environ.get("CONDA_DEFAULT_ENV", "None")
    if conda_env != "None":
        assert os.path.exists(
            conda_env
        ), f"Conda env {conda_env} does not exist"
        python_binary = os.path.join(conda_env, "bin", "python3.10")
        assert os.path.exists(
            python_binary
        ), f"Python binary {python_binary} does not exist"
    else:
        python_binary = "python"
    return python_binary, conda_env


def read_last_bytes(file_path, n_bytes=1024):
    with open(file_path, "r") as f:
        f.seek(0, 2)  # Seek to end of file
        size = f.tell()  # Get file size
        f.seek(max(0, size - n_bytes))  # Go back 1024 bytes from end
        return f.read()


@pytest.mark.skipif(SKIP_TESTS, reason="Skip tests when debugging")
def test_runner_script(test_env):
    """Test that the runner script runs without errors."""

    # Run the script with test environment
    log_file_path = os.path.join(test_env["temp_dir"], "test_log.out")

    python_binary, conda_env = get_python_binary()
    cmd = [
        python_binary,
        "-m",
        "stnd.run_from_csv.__main__",
        "--csv_path",
        test_env["csv_path_runner"],
        "--conda_env",
        conda_env,
        "--run_locally",
        "--log_file_path",
        log_file_path,
    ]
    df = compare_csv_to_canonical(
        cmd,
        log_file_path,
        test_env["csv_path_runner"],
        os.path.join(CANONICAL_FOLDER, "canonical_csv_runner.csv"),
    )
    run_folder = df["run_folder"].iloc[0]
    stdout_path = os.path.join(test_env["temp_dir"], run_folder, "stdout.txt")
    stderr_path = os.path.join(test_env["temp_dir"], run_folder, "stderr.txt")
    stdout = read_last_bytes(stdout_path)
    stderr = read_last_bytes(stderr_path)
    assert "Hello, stdout" in stdout, "Hello, stdout not found"
    assert "Hello, stderr" in stderr, "Hello, stderr not found"


def compare_csv_to_canonical(cmd, log_file_path, df_path, canonical_df_path):
    # Run the command and check for errors
    result = subprocess.run(cmd, capture_output=True, text=True)
    time.sleep(SMALL_SLEEP_TIME)  # make sure that status column is created

    # Check that the script ran successfully
    assert result.returncode == 0, f"Script failed with error: {result.stderr}"

    # Check that the output file was created
    assert os.path.exists(log_file_path), "Log file was not created"

    # Check that the CSV was updated
    df = pd.read_csv(df_path)
    num_sleeps = 0
    while (
        df["status"].iloc[0] in ["Submitted", "Running"]
        and num_sleeps < MAX_SLEEPS
    ):
        # Wait a bit for the job to complete
        time.sleep(SLEEP_TIME)
        df = pd.read_csv(df_path)
        num_sleeps += 1
    assert df["status"].iloc[0] == "Completed", "CSV status was not updated"

    # Load canonical CSV for comparison
    canonical_df = pd.read_csv(canonical_df_path)

    # Check that all expected columns exist in both dataframes
    assert set(canonical_df.columns) == set(
        df.columns
    ), "CSV columns do not match canonical CSV"

    # Check run_folder column exists and contains string
    for col in UNIQUE_COLUMNS:
        assert col in df.columns, f"{col} column missing"
        assert isinstance(df[col].iloc[0], str), f"{col} value is not a string"

    # Compare all columns except run_folder
    cols_to_compare = [
        col for col in canonical_df.columns if col not in UNIQUE_COLUMNS
    ]
    for col in cols_to_compare:
        for row in range(canonical_df.shape[0]):
            value_in_df = df[col].iloc[row]
            if isinstance(value_in_df, str):
                value_in_df = value_in_df.replace(CUR_FOLDER, ".")
            canonical_value = canonical_df[col].iloc[row]
            if not isinstance(canonical_value, str) and np.isnan(
                canonical_value
            ):
                assert np.isnan(
                    value_in_df
                ), f"Value in column {col} should be NaN"
            else:
                assert (
                    value_in_df == canonical_value
                ), f"Column {col} does not match canonical CSV"

    return df


@pytest.mark.skipif(SKIP_TESTS, reason="Skip tests when debugging")
def test_main_script(test_env):
    """Test that the main script runs without errors."""

    # Run the script with test environment
    log_file_path = os.path.join(test_env["temp_dir"], "test_log.out")

    python_binary, conda_env = get_python_binary()
    cmd = [
        python_binary,
        "-m",
        "stnd.run_from_csv.__main__",
        "--csv_path",
        test_env["csv_path"],
        "--conda_env",
        conda_env,
        "--run_locally",
        "--log_file_path",
        log_file_path,
    ]

    compare_csv_to_canonical(
        cmd,
        log_file_path,
        test_env["csv_path"],
        os.path.join(CANONICAL_FOLDER, "canonical_csv.csv"),
    )


@pytest.mark.skipif(SKIP_TESTS, reason="Skip tests when debugging")
def test_sbatch_scripts(test_env):
    """Test that the sbatch scripts are created correctly."""

    # Run the script with test environment
    log_file_path = os.path.join(test_env["temp_dir"], "test_log_sbatch.out")

    python_binary, conda_env = get_python_binary()
    cmd = [
        python_binary,
        "-m",
        "stnd.run_from_csv.__main__",
        "--csv_path",
        test_env["csv_path"],
        "--conda_env",
        conda_env,
        "--log_file_path",
        log_file_path,
        "--debug",
    ]

    # Run the command and check for errors
    result = subprocess.run(cmd, capture_output=True, text=True)
    canonical_path = os.path.join(CANONICAL_FOLDER, "canonical_sbatch.txt")
    with open(canonical_path, "r") as f:
        canonical_contents = f.read()
    for line in result.stdout.split("\n"):
        if "COMMAND TO SUBMIT" in line:
            sbatch_file = line.split("sbatch ")[-1]
            # Read and compare sbatch file contents
            with open(sbatch_file, "r") as f:
                sbatch_contents = f.read()

            # Replace random temp folder hash with generic <hash> placeholder
            tmp_hash = sbatch_contents.split("/run_from_csv", 1)[-1].split("/")[
                0
            ]
            sbatch_contents = sbatch_contents.replace(tmp_hash, "<hash>")
            autogen_config = sbatch_contents.split("autogenerated/")[-1].split(
                ".yaml"
            )[0]
            sbatch_contents = (
                sbatch_contents.replace(
                    autogen_config, "<autogenerated_config>"
                ).replace(STND_ROOT, ".")
                + "\n"
            )
            before_python = None
            for line in sbatch_contents.split("\n"):
                if "python " in line:
                    before_python = line.split("python ")[0]
            assert before_python is not None, "python line not found"
            sbatch_contents = sbatch_contents.replace(before_python, "")

            assert (
                sbatch_contents == canonical_contents
            ), "Generated sbatch file does not match canonical file"


def cleanup_test_env(test_env):
    """Clean up test environment after tests complete."""
    # Remove temporary directory and all contents
    if os.path.exists(test_env["temp_dir"]):
        shutil.rmtree(test_env["temp_dir"])

    # Remove any generated CSV files
    if os.path.exists(test_env["csv_path"]):
        os.remove(test_env["csv_path"])

    # Clean up any autogenerated folders
    autogen_path = os.path.join(CONFIGS_FOLDER, "autogenerated")
    if os.path.exists(autogen_path):
        shutil.rmtree(autogen_path)


@pytest.mark.skipif(SKIP_TESTS, reason="Skip tests when debugging")
def test_run_from_csv_is_callable(test_env):
    python_binary, conda_env = get_python_binary()
    cmd = f"{python_binary} -m stnd.run_from_csv"

    # change work dir to make sure that stnd folder is not in sys.path
    result = subprocess.run(
        cmd.split(), capture_output=True, text=True, cwd=test_env["temp_dir"]
    )
    assert "the following arguments are required: --csv_path" in result.stderr
