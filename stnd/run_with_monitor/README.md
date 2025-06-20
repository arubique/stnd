# STND Run With Monitor

A job management system for running and monitoring experiments defined in CSV files or Google Sheets. This system handles job submission to SLURM clusters, real-time monitoring, and automatic status updates back to spreadsheets.

## Overview

The `run_with_monitor` module provides:

- **CSV/Google Sheets Integration**: Define experiments in spreadsheets with configuration parameters
- **SLURM Job Management**: Automatic submission and monitoring of cluster jobs
- **Real-time Monitoring**: Track job status, resource usage, and completion
- **Dynamic Configuration**: Generate experiment configs from templates with parameter overrides
- **Socket Communication**: Real-time updates between jobs and monitoring system
- **Multi-cluster Support**: Automatic detection of cluster regions (Galvani/Ferranti)
- **Concurrent Execution**: Parallel job processing with configurable limits

## Quick Start

### Basic Usage

```bash
# Run from CSV file
python -m stnd.run_with_monitor --csv_path /path/to/experiments.csv

# Run from Google Sheets  
python -m stnd.run_with_monitor --csv_path "https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID::WORKSHEET_NAME" --use_socket

# Run locally (no SLURM)
python -m stnd.run_with_monitor --csv_path experiments.csv --run_locally

# Limit concurrent jobs
python -m stnd.run_with_monitor --csv_path experiments.csv --max_concurrent_jobs 5
```

### Example from your previous usage:
```bash
python -m stnd.run_with_monitor --csv_path "https://docs.google.com/spreadsheets/d/14Z7FCA9ryrhP2oSVW6OytnjRyWhUx8bM91FSrNvG6b8::Sheet1" --use_socket
```

## Command Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--csv_path` | Path to CSV file or Google Sheets URL | **Required** |
| `--conda_env` | Conda environment name | `base` |
| `--run_locally` | Run jobs locally instead of SLURM | `False` |
| `--use_socket` | Enable socket communication for monitoring | `False` |
| `--max_concurrent_jobs` | Maximum concurrent jobs (-1 = unlimited) | `-1` |
| `--expand` | Expand CSV by cartesian product | `False` |
| `--log_file_path` | Path for log files | `tmp/tmp_log_for_run_from_csv.out` |
| `--disable_local_loging` | Disable wandb/gdrive for local runs | `False` |

## CSV/Spreadsheet Format

Your CSV must contain these required columns:

### Required Columns
- `whether_to_run`: `1` to run, `0` to skip
- `path_to_default_config`: Path to base configuration YAML
- `path_to_main`: Path to main Python script to execute

### SLURM Configuration (prefix with `slurm:`)
- `slurm:partition`: SLURM partition name
- `slurm:time`: Job time limit (e.g., "02:00:00")
- `slurm:mem`: Memory requirement (e.g., "16G")
- `slurm:cpus-per-task`: CPU cores
- `slurm:gres`: GPU resources (e.g., "gpu:1")

### Configuration Overrides (prefix with `delta:`)
- `delta:learning_rate`: Override config parameter
- `delta:model.hidden_size`: Override nested parameter

### Example CSV Structure
```csv
whether_to_run,path_to_default_config,path_to_main,slurm:partition,slurm:time,delta:learning_rate,delta:batch_size
1,/path/to/config.yaml,/path/to/train.py,gpu_a100,02:00:00,0.001,32
1,/path/to/config.yaml,/path/to/train.py,gpu_a100,02:00:00,0.01,64
```

## How It Works

### 1. Configuration Processing
- Reads CSV/Google Sheets and validates required columns
- Fetches default configuration files from specified paths
- Applies delta overrides to create experiment-specific configs
- Handles placeholders like `__ROW__` and `__WORKSHEET__`

### 2. Job Submission
- Generates SLURM batch scripts with specified resources
- Creates conda environment activation commands
- Submits jobs to appropriate cluster partitions
- Tracks job IDs and submission status

### 3. Real-time Monitoring
- Uses socket communication for live job updates
- Monitors SLURM job status (PENDING, RUNNING, COMPLETED, FAILED)
- Tracks resource usage and execution time
- Updates spreadsheets with current status

### 4. Status Updates
- Updates CSV/Google Sheets with job status
- Records SLURM job IDs and exit codes
- Maintains last update timestamps
- Handles job completion and cleanup

## Google Sheets Setup

### 1. Generate Credentials
Follow [gspread OAuth instructions](https://docs.gspread.org/en/latest/oauth2.html#for-end-users-using-oauth-client-id):
- Create Google Cloud project
- Enable Google Sheets API
- Create OAuth 2.0 credentials
- Download and save as `~/.config/gauth/credentials.json`

### 2. Sheet URL Format
Use this format: `https://docs.google.com/spreadsheets/d/SHEET_ID::WORKSHEET_NAME`

Example: `https://docs.google.com/spreadsheets/d/14Z7FCA9ryrhP2oSVW6OytnjRyWhUx8bM91FSrNvG6b8::Sheet1`

## Cluster Support

### Automatic Detection
The system automatically detects cluster regions:
- **Galvani**: Supports A100, 2080 GPUs
- **Ferranti**: Supports H100 GPUs  
- **Unknown**: Uses specified partitions

### GPU Compatibility
Jobs are automatically filtered based on cluster capabilities:
- H100 jobs skip on Galvani cluster
- A100/2080 jobs skip on Ferranti cluster

## Advanced Features

### Socket Communication
Enable with `--use_socket` for real-time job monitoring:
- Jobs send status updates via TCP sockets
- Monitor receives live progress information
- Automatic server cleanup on completion

### Configuration Expansion
Use `--expand` to create cartesian products:
- Expands parameter combinations automatically
- Creates new worksheet with expanded experiments
- Useful for hyperparameter sweeps

### Concurrent Job Control
Limit parallel execution with `--max_concurrent_jobs`:
- Prevents cluster overload
- Queues jobs when limit reached
- Monitors completion to start queued jobs

## Status Columns

The system adds these columns to track progress:

| Column | Description |
|--------|-------------|
| `status_monitor` | Current job status |
| `exit_code_monitor` | Job exit code |
| `slurm_job_id_monitor` | SLURM job identifier |
| `last_update_monitor` | Last status update time |

## Example Workflow

1. **Prepare CSV**: Define experiments with configs and parameters
2. **Submit Jobs**: `python -m stnd.run_with_monitor --csv_path experiments.csv --use_socket`
3. **Monitor Progress**: Watch real-time updates in terminal and spreadsheet
4. **Review Results**: Check status columns and log files for completion

## Troubleshooting

### Common Issues
- **Missing credentials**: Ensure `~/.config/gauth/credentials.json` exists
- **Config not found**: Verify `path_to_default_config` paths are correct
- **Permission denied**: Check file permissions and cluster access
- **Socket timeout**: Increase timeout or disable socket mode

### Log Files
Check log files for detailed error information:
- Default location: `tmp/tmp_log_for_run_from_csv.out`
- SLURM logs: Generated per job in specified directories

## Migration from stuned

If migrating from the old `stuned` package:

**Old command:**
```bash
python -m stuned.run_from_csv --csv_path URL --use_socket
```

**New command:**
```bash
python -m stnd.run_with_monitor --csv_path URL --use_socket
```

All functionality remains the same, just the module path has changed.
