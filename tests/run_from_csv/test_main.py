import os
import tempfile
import shutil
import pytest
import yaml
import pandas as pd
import sys
import subprocess
import time


# local imports
CUR_FOLDER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(CUR_FOLDER)))),
)
from stnd.utility.utils import (
    optionally_make_parent_dir,
    run_cmd_through_popen,
)

sys.path.pop(0)


UNIQUE_COLUMNS = ["run_folder", "walltime"]
TOTAL_ROWS = 3
STND_ROOT = os.path.dirname(os.path.dirname(CUR_FOLDER))


def create_test_csv(csv_path, config_path):
    """Create a test CSV file with minimal required columns."""
    path_to_main = os.path.join(CUR_FOLDER, "executable.py")
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
        parent_git_dir = os.path.join(
            os.path.dirname(os.path.dirname(CUR_FOLDER)), ".git"
        )
        os.symlink(parent_git_dir, os.path.join(temp_dir, ".git"))

        os.environ["PROJECT_ROOT_PROVIDED_FOR_STUNED"] = temp_dir
        # Create test files
        csv_path = os.path.join(temp_dir, "test.csv")
        config_path = os.path.join(CUR_FOLDER, "config.yaml")

        # optionally can create config inplace: create_test_config(config_path)
        create_test_csv(csv_path, config_path)

        # Create necessary directories
        os.makedirs(os.path.join(temp_dir, "experiment_configs"), exist_ok=True)
        os.makedirs(os.path.join(temp_dir, "tmp"), exist_ok=True)

        env_dict = {
            "temp_dir": temp_dir,
            "csv_path": csv_path,
            "config_path": config_path,
        }

        yield env_dict
        # Register cleanup to run after all tests
        request.addfinalizer(lambda: cleanup_test_env(env_dict))


def get_python_binary():
    # on github everything is in the base env, but when debugging
    # we need to use the envs/env_stnd env
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


# @pytest.mark.skip(reason="Temporarily disabled")
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

    # Run the command and check for errors
    result = subprocess.run(cmd, capture_output=True, text=True)
    time.sleep(1)  # make sure that status column is created

    # Check that the script ran successfully
    assert result.returncode == 0, f"Script failed with error: {result.stderr}"

    # Check that the output file was created
    assert os.path.exists(log_file_path), "Log file was not created"

    # Check that the CSV was updated
    df = pd.read_csv(test_env["csv_path"])
    if df["status"].iloc[0] in ["Submitted", "Running"]:
        # Wait a bit for the job to complete
        time.sleep(5)
        df = pd.read_csv(test_env["csv_path"])
    else:
        assert df["status"].iloc[0] == "Completed", "CSV status was not updated"

    # Load canonical CSV for comparison
    canonical_df = pd.read_csv(os.path.join(CUR_FOLDER, "canonical_csv.csv"))

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
        for row in range(TOTAL_ROWS):
            value_in_df = df[col].iloc[row]
            if isinstance(value_in_df, str):
                value_in_df = value_in_df.replace(CUR_FOLDER, ".")
            canonical_value = canonical_df[col].iloc[row]
            assert (
                value_in_df == canonical_value
            ), f"Column {col} does not match canonical CSV"

            # Clean up autogenerated folder
            autogen_path = os.path.join(CUR_FOLDER, "autogenerated")
            if os.path.exists(autogen_path):
                shutil.rmtree(autogen_path)


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
    canonical_path = os.path.join(CUR_FOLDER, "canonical_sbatch.txt")
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
    autogen_path = os.path.join(CUR_FOLDER, "autogenerated")
    if os.path.exists(autogen_path):
        shutil.rmtree(autogen_path)
