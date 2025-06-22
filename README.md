# stnd

This repository contains utility code for running and organizing structured experiments in a reproducible and debuggable way — freeing up mental overhead. It replaces manual bash scripting, log handling, and job submission (e.g., via Slurm) with a streamlined workflow. Once set up, all you need to do to run a new experiment is to specify relevant arguments in a Google Sheet, copy the auto-generated command to the terminal and press Enter. The system handles the rest.

As an output you get Google Sheet or CSV table that you can extend with new experiments later. Each run corresponds to a row containing the run arguments, links to logs and Weights & Biases (if enabled), and any metrics or values the user chooses to store from the script output. All logs by default store full experiment config, python environment, GitHub commit hash, and the associated code diff to make results reproducible.

See [scheduler guide](./stnd/run_from_csv/RUN_FROM_CSV_README.md) for details.
