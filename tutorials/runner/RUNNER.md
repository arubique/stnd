This tutorial demonstrates how to run any command/script with the scheduler without writing any wrapping code for the original script. Config file and results table will still be needed. The sections below will explain how to prepare these files and run the experiment.

## Preliminaries

### Be aware of the quick start guide

Before starting this tutorial, make sure you:

- Understand the gist of [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md).
- Have an [Anaconda](https://www.anaconda.com/) environment with the `stnd` package installed as described [here](../../README.md#installation).

## Prepare experiment script

In contrast to the [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md), the command or script you want to run with the runner does not need to be preconfigured — it can be used as-is.

For demonstration purposes, we will use the file `./runner_target.py` as the target script.

You do not need to understand the internal logic of `./runner_target.py`. All you need to know is that when it is called with the flags `--long_flag` and `-s`, it prints the line `answer: <value>`, where `<value>` is computed as a sum of 42 with the number provided via the keyword argument `--user_number`.

## Prepare default config

Same as in [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md) we need to define default config before running the demo experiment.

For demonstration, we've provided `./runner_config.yml` that specifies the arguments used by `runner_target.py`:

```yaml
exec_path: <will be defined in runner_results.csv>
is_python: <will be defined in runner_results.csv>
conda_env: <will be defined in runner_results.csv>
kwargs: {}
two_dash_flags: []
single_dash_flags: []
take_last_dict: {}
logging:
  use_wandb: false
params:
  random_seed: 42
```

It introduces the following new arguments:

- `exec_path`: Path to the executable or script to be run by the runner.
- `is_python`: If `True`, the command is executed as `python <exec_path>`. Otherwise, `<exec_path>` is called directly.
- `conda_env`: Name of the conda environment to activate before running the Python binary. Must be omitted if `is_python` is `False`.
- `kwargs`: Dictionary of keyword arguments passed to the command.
- `two_dash_flags`: List of flags prefixed with `--` to be included in the command.
- `single_dash_flags`: List of flags prefixed with `-` to be included in the command.
- `take_last_dict`: Dictionary of regular expressions used to extract values from the script's output. See [this section](#take_last_dict) for details.

The rest of the arguments are the same as in [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md#prepare-default-config).

## Prepare results table

Once `runner_config.yml` is ready, you can create a results table template to store all experiments similarly to [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md#prepare-results-table).

For demonstration, we've provided `./runner_results.csv`, which will store each experiment's configuration parameters and results.

| path_to_default_config             | path_to_main | whether_to_run | delta:exec_path                      | delta:conda_env | delta:is_python | delta:kwargs/user_number | delta:two_dash_flags | delta:single_dash_flags | delta:take_last_dict/answer      |
|-----------------------------------|--------------|----------------|--------------------------------------|------------------|------------------|---------------------------|-----------------------|---------------------------|-----------------------------------|
| ./tutorials/runner/runner_config.yaml | `__RUNNER__`   | 1              | ./tutorials/runner/runner_target.py | None             | True             | 10                        | [long_flag]          | [s]                      | answer: (__B__d+)                 |

To understand what `__B__` means, please refer to [this section](#take_last_dict).
`two_dash_flags` contains flag `long_flag` and `single_dash_flags` contains flag `s`, so that after running the script `runner_target.py` it will print `answer: <value>` as described in this [section](#prepare-experiment-script).

The only conceptual difference from `results.csv` in [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md#prepare-results-table) is `__RUNNER__` keyword in `path_to_main` column and different arguments to account for the structure of `runner_config.yaml`.
The `__RUNNER__` keyword is needed to let the scheduler know that you want to run the experiment with a runner.

## Run experiment

Once the results table `runner_results.csv` is filled in, you're ready to run the experiments.

Run the following command, after substituting `<your env>` and `<repo with experiments>` same as described in [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md#run-experiment):

```
export ENV=<your env> && export PROJECT_ROOT_PROVIDED_FOR_STUNED=<repo with experiments> && conda activate $ENV && python -m stnd.run_from_csv.__main__ --csv_path $PROJECT_ROOT_PROVIDED_FOR_STUNED/tutorials/runner/runner_results.csv --run_locally --conda_env $ENV
```

<!-- export ENV=/Users/arubique/github/stnd/envs/stnd_env && export PROJECT_ROOT_PROVIDED_FOR_STUNED=/Users/arubique/github/stnd/ && conda activate $ENV && python -m stnd.run_from_csv.__main__ --csv_path $PROJECT_ROOT_PROVIDED_FOR_STUNED/tutorials/runner/runner_results.csv --run_locally --conda_env $ENV -->

After the command completion, `runner_results.csv` will look like `filled_runner_results.csv` with all added columns and logged values:

| path_to_default_config             | path_to_main | whether_to_run | delta:exec_path                      | delta:conda_env | delta:is_python | delta:kwargs/user_number | delta:two_dash_flags | delta:single_dash_flags | delta:take_last_dict/answer | status    | run_folder                                                                                     | job id   | walltime          | answer |
|-----------------------------------|--------------|----------------|--------------------------------------|------------------|------------------|---------------------------|-----------------------|---------------------------|-------------------------------|-----------|-----------------------------------------------------------------------------------------------|----------|--------------------|--------|
| ./tutorials/runner/runner_config.yaml | `__RUNNER__`   | 0              | ./tutorials/runner/runner_target.py | None             | True             | 10                        | [long_flag]          | [s]                      | answer: (__B__d+)             | Completed | /Users/arubique/github/stnd/experiments/runner/2025-07-03_18:28:59.879372---dfb9ddbaefdeb8aee21f---25068 | Not found | 0:00:00.217823     | 52     |

As we can see, the `answer` column contains the value `52`, which is exactly what we expected to be printed in the line `answer: <value>`, as described in [this section](#prepare-experiment-script). This value was extracted from the output using the regular expression provided in the `take_last_dict/answer` argument, which is explained in more detail in [this section](#take_last_dict).

The process of modifying the results table and creating experiment/config files is identical to the one described in the [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md#run-experiment).
Please refer to that section for detailed instructions.

## Parsing values from output

Since we do not modify the original script (`runner_target.py`) in this tutorial, we need another way to specify which values should be logged to the results table. This is handled by the `take_last_dict` argument.

### `take_last_dict`

This argument is a dictionary of the form `{"variable_name": "regex"}`. While running the experiment, any value printed to `stdout` that matches a given regex will be extracted and recorded under the corresponding `variable_name` column in the results table, in the row associated with that experiment.

If multiple matches occur, only the most recent one will be logged — the newer value overwrites the older one. This behavior is the reason behind the name `take_last`.

Note: Since backslashes (`\`) can cause parsing issues in the results table, please use the placeholder keyword `__B__` instead. It will be automatically replaced with `\` by the scheduler during execution.







