import os
import tempfile
import shutil
import pytest
import yaml
import pandas as pd
from pathlib import Path
import sys

# local imports
sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
)
from stnd.utility.utils import optionally_make_dir

sys.path.pop(0)


def create_test_csv(csv_path, config_path):
    """Create a test CSV file with minimal required columns."""
    data = {
        "path_to_default_config": [config_path],
        "path_to_main": ["src/stuned/run_cmd/main.py"],
        "whether_to_run": ["1"],
        "status": ["pending"],
        "delta_test_param": ["test_value"],
    }
    df = pd.DataFrame(data)
    df.to_csv(csv_path, index=False)


def create_test_config(config_path):
    """Create a test config file."""
    config = {
        "test_param": "default_value",
        "logging": {
            "output_csv": {
                "path": "test_output.csv",
                "row_number": 0,
                "spreadsheet_url": None,
                "worksheet_name": None,
            }
        },
    }
    with open(config_path, "w") as f:
        yaml.dump(config, f)


@pytest.fixture
def test_env():
    """Set up test environment with temporary files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"temp_dir for testing: {temp_dir}")

        os.environ["PROJECT_ROOT_PROVIDED_FOR_STUNED"] = temp_dir
        # Create test files
        csv_path = os.path.join(temp_dir, "test.csv")
        config_path = os.path.join(temp_dir, "test_config.yaml")

        create_test_config(config_path)
        create_test_csv(csv_path, config_path)

        # Create necessary directories
        os.makedirs(os.path.join(temp_dir, "experiment_configs"), exist_ok=True)
        os.makedirs(os.path.join(temp_dir, "tmp"), exist_ok=True)

        yield {
            "temp_dir": temp_dir,
            "csv_path": csv_path,
            "config_path": config_path,
        }


def test_main_script(test_env):
    """Test that the main script runs without errors."""
    import subprocess

    # Run the script with test environment
    cmd = [
        "python",
        "-m",
        "stnd.run_from_csv.__main__",
        "--csv_path",
        test_env["csv_path"],
        "--conda_env",
        "base",  # Use base environment for testing
        "--run_locally",
        "--log_file_path",
        os.path.join(test_env["temp_dir"], "tmp", "test_log.out"),
    ]

    # Run the command and check for errors
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Check that the script ran successfully
    assert result.returncode == 0, f"Script failed with error: {result.stderr}"

    # Check that the output file was created
    log_file = os.path.join(test_env["temp_dir"], "tmp", "test_log.out")
    assert os.path.exists(log_file), "Log file was not created"

    # Check that the CSV was updated
    df = pd.read_csv(test_env["csv_path"])
    print(f"df: {df}")
    assert df["status"].iloc[0] == "submitted", "CSV status was not updated"
    assert (
        df["whether_to_run"].iloc[0] == "0"
    ), "CSV whether_to_run was not updated"
