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
STND_ROOT = os.path.dirname(os.path.dirname(CUR_FOLDER))
sys.path.insert(
    0,
    STND_ROOT,
)
from stnd.utility.utils import (
    optionally_make_parent_dir,
    run_cmd_through_popen,
)

sys.path.pop(0)


UNIQUE_COLUMNS = ["run_folder", "walltime"]
TOTAL_ROWS = 3
MAX_SLEEPS = 100
SMALL_SLEEP_TIME = 1
SLEEP_TIME = 5


def create_test_csv(csv_path, config_path, cluster_type="slurm"):
    """Create a test CSV file with minimal required columns."""
    path_to_main = os.path.join(CUR_FOLDER, "executable.py")
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
    else:
        assert cluster_type == "condor", "Invalid cluster type"
        data = {
            "path_to_default_config": [config_path],
            "path_to_main": [path_to_main],
            "whether_to_run": ["1"],
            "condor:cpus-per-task": ["4"],
            "condor:partition": ["a100"],
            "condor:bid": ["1"],
            "condor:output": ["logs/job_stdout.out"],
            "condor:error": ["logs/job_stderr.err"],
            "delta:logging/wandb/netrc_path": ["~/.netrc"],
            "delta:logging/use_wandb": ["FALSE"],
            "delta:initialization_type": ["zeros"],
            "delta:image/color": ["red"],
            "env_var:CUDA_VISIBLE_DEVICES": [
                "0__COMMA__1__COMMA__2__COMMA__3__COMMA__4__COMMA__5__COMMA__6__COMMA__7"
            ],
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
        csv_path_condor = os.path.join(temp_dir, "test_condor.csv")
        config_path = os.path.join(CUR_FOLDER, "config.yaml")

        # optionally can create config inplace: create_test_config(config_path)
        create_test_csv(csv_path, config_path)
        create_test_csv(csv_path_condor, config_path, cluster_type="condor")

        # Create necessary directories
        os.makedirs(os.path.join(temp_dir, "experiment_configs"), exist_ok=True)
        os.makedirs(os.path.join(temp_dir, "tmp"), exist_ok=True)

        env_dict = {
            "temp_dir": temp_dir,
            "csv_path": csv_path,
            "csv_path_condor": csv_path_condor,
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
    time.sleep(SMALL_SLEEP_TIME)  # make sure that status column is created

    # Check that the script ran successfully
    assert result.returncode == 0, f"Script failed with error: {result.stderr}"

    # Check that the output file was created
    assert os.path.exists(log_file_path), "Log file was not created"

    # Check that the CSV was updated
    df = pd.read_csv(test_env["csv_path"])
    num_sleeps = 0
    while (
        df["status"].iloc[0] in ["Submitted", "Running"]
        and num_sleeps < MAX_SLEEPS
    ):
        # Wait a bit for the job to complete
        time.sleep(SLEEP_TIME)
        df = pd.read_csv(test_env["csv_path"])
        num_sleeps += 1
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


# @pytest.mark.skip(reason="Temporarily disabled")
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

    check_submission_script(cmd, "slurm")


# @pytest.mark.skip(reason="Temporarily disabled")
def test_condor_scripts(test_env):
    """Test that the condor scripts are created correctly."""

    # Run the script with test environment
    log_file_path = os.path.join(test_env["temp_dir"], "test_log_condor.out")

    python_binary, conda_env = get_python_binary()
    cmd = [
        python_binary,
        "-m",
        "stnd.run_from_csv.__main__",
        "--csv_path",
        test_env["csv_path_condor"],
        "--conda_env",
        "<env_for_condor>",
        "--log_file_path",
        log_file_path,
        "--debug",
        "--cluster_type",
        "condor",
    ]
    check_submission_script(cmd, "condor")


def check_submission_script(cmd, cluster_type):
    # Run the command and check for errors
    result = subprocess.run(cmd, capture_output=True, text=True)

    if cluster_type == "condor":
        canonical_path = os.path.join(CUR_FOLDER, f"canonical_condor.txt")
    else:
        canonical_path = os.path.join(CUR_FOLDER, f"canonical_sbatch.txt")
    with open(canonical_path, "r") as f:
        canonical_contents = f.read()

    if cluster_type == "condor":
        with open(
            os.path.join(CUR_FOLDER, f"canonical_condor_sh_file.txt"), "r"
        ) as f:
            canonical_contents_sh_file = f.read()
    else:
        canonical_contents_sh_file = None

    condor_executable_path = None
    for line in result.stdout.split("\n"):
        if "COMMAND TO SUBMIT" in line:
            if cluster_type == "condor":
                submission_file = line.split("condor_submit_bid ")[-1].split(
                    " "
                )[-1]
            else:
                submission_file = line.split("sbatch ")[-1]
            # Read and compare sbatch file contents
            with open(submission_file, "r") as f:
                submission_contents = f.read()

            if cluster_type == "condor":
                condor_executable_path = submission_contents.split(
                    "executable = "
                )[-1].split("\n")[0]
                submission_contents = submission_contents.replace(
                    condor_executable_path, "<executable>"
                )
                assert (
                    submission_contents == canonical_contents
                ), "Generated condor submission file does not match canonical file"
                # Condor has 2 submission files, now reading the second one
                with open(condor_executable_path, "r") as f:
                    submission_contents = f.read()
                assert canonical_contents_sh_file is not None
                canonical_contents = canonical_contents_sh_file

            else:
                # Replace random temp folder hash with generic <hash> placeholder
                tmp_hash = submission_contents.split("/run_from_csv", 1)[
                    -1
                ].split("/")[0]
                submission_contents = submission_contents.replace(
                    tmp_hash, "<hash>"
                )
                before_python = None
                for line in submission_contents.split("\n"):
                    if "python " in line:
                        before_python = line.split("python ")[0]
                assert before_python is not None, "python line not found"
                submission_contents = submission_contents.replace(
                    before_python, ""
                )
            autogen_config = submission_contents.split("autogenerated/")[
                -1
            ].split(".yaml")[0]
            submission_contents = (
                submission_contents.replace(
                    autogen_config, "<autogenerated_config>"
                ).replace(STND_ROOT, ".")
                + "\n"
            )
            submission_contents = submission_contents.replace(
                os.path.expanduser("~"), "~"
            )

            assert (
                submission_contents == canonical_contents
            ), "Submission file does not match canonical file"


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


# @pytest.mark.skip(reason="Temporarily disabled")
def test_run_from_csv_is_callable(test_env):
    python_binary, conda_env = get_python_binary()
    cmd = f"{python_binary} -m stnd.run_from_csv"

    # change work dir to make sure that stnd folder is not in sys.path
    result = subprocess.run(
        cmd.split(), capture_output=True, text=True, cwd=test_env["temp_dir"]
    )
    assert "the following arguments are required: --csv_path" in result.stderr
