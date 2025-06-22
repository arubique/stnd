# Scheduler Overview
The scheduler's goal is to organize all experiments in a single results table, where each row represents one experiment and stores all the information needed for reproduction and analysis.

This file serves as a table of contents for tutorials covering the scheduler's functionality.

## Contents

### Quick start guide

[Quick start guide](../../tutorials/quick_start_guide/QUICK_START_GUIDE.md) for using the scheduler with local runs (no internet required). Results table is stored in a local .csv file. Just wrap your script with our code and call the corresponding logger's commands as needed.

### Running Any Script with the Scheduler

[Guide](../../tutorials/runner/RUNNER.md) for running any command/script with the scheduler without wrapping it or calling any loggers manually. Offers a simpler setup with limited functionality.

### Syncing results tables, configs, and logs with Google Sheets and Drive

[Guide](../../tutorials/syncing/SYNC.md) for syncing with Google Sheets and Drive. The results table moves from local .csv file to Google Sheets, and you can optionally sync default configs, stdout, and stderr logs to Google Drive. These files become accessible via permanent links in the results table allowing for simpler tracking of your experiments.

### Automating table editing in Google Sheets via JavaScript Macros

[Guide](../../tutorials/macros/MACROS.md) for simplifying Google Sheets setup with templates, auto-filled entries, conditional formatting, and easy management of experiment rows.

### Using the scheduler with High Performance Computing (HPC) Systems (e.g., Slurm)

[Guide](../../tutorials/cluster/CLUSTER.md) for enabling the scheduler to automatically request compute nodes and run jobs in an HPC cluster, with all outputs and metadata logged in the results table.

### Scheduler's arguments and constants reference.

[Explanation](../../tutorials/reference/REFERENCE.md) of scheduler arguments and constants, including how they are interpreted and mapped by the scheduler when interacting with the results table.
