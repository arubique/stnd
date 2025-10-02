This file contains a reference table of common placeholders and notations used to simplify experiment scheduling.

Placeholders are automatically substituted by the scheduler script after experiment submission, as shown in the [Placeholders Table](#placeholders-table) section.
In the [Reference Table](#reference-table) section, we also provide examples of how to specify basic objects like lists when submitting experiments.


## Preliminaries

### Be aware of the quick start guide

Before starting this tutorial, make sure you:

- Please take a look at the [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md) to understand the key concepts, such as the **results table** and experiments-rows mapping in it.

## Placeholders table

| Placeholder | Description |
| ------------ | ----------- |
| `__ROW__` | The row number in the results table. Useful for generating unique values for each row without manually updating them. For example, you can use the same string for your model checkpoint, like `my_checkpoint-__ROW__.pkl`, in each row — each experiment will automatically get a unique checkpoint path and avoid overwriting files. |
| `__WORKSHEET__` | The name of the worksheet (tab) in the results table. Helpful for identifying or logging which worksheet the experiment came from. |
| `__COMMA__`    | Substituted with a comma (`,`). Useful when you need to pass a comma-separated list inside a single cell without breaking the .csv table structure. |
| `__B__`        | Substituted with a backslash (`\`). Handy for escaping characters (e.g. in regexes as [here](../runner/RUNNER.md#take_last_dict)) or creating multi-line commands. |
| `__RUNNER__`   | The path to the runner script, as described in the [runner tutorial](../runner/RUNNER.md#prepare-results-table). Allows for flexible referencing of the execution script without hardcoding paths. |
| `__COL:<col_name>__` | Substituted with the value from the column named `<col_name>` in the same row. Useful for referencing values from other columns within the same row. For example, if you have columns `model_name` and `checkpoint_path`, you can use `__COL:checkpoint_path__/__COL:model_name__.pkl` to create a path that combines values from both columns. If the referenced column doesn't exist, an error will be raised. |

## Reference table

| Notation | Description |
|--------------------|-------------|
| `[a b c]` | Creates a list with elements `a`, `b`, and `c`. Note that commas are not used to accommodate the constraint that the results table cannot contain commas, as explained [here](../quick_start_guide/QUICK_START_GUIDE.md#prepare-results-table). |
| `delta:` | Prefix used to specify changes to the default configuration. For example, if you have a default config with `learning_rate: 0.1` and want to change it to 0.01 for a specific experiment, you can add a column `delta:learning_rate` with value `0.01`. The scheduler will automatically update the default config with this new value. For nested configurations, use `/` as a separator inside config, e.g., `delta:optimizer/learning_rate`. For examples of using the `delta:` prefix, see [this tutorial](../quick_start_guide/QUICK_START_GUIDE.md#prepare-results-table). |
| `slurm:` | Prefix used to specify SLURM job submission parameters. For example, `slurm:partition` with value `gpu` will set the partition to `gpu` when submitting the job to SLURM. Common parameters include `partition`, `time` (job time limit), `mem` (memory request), `cpus-per-task`, etc. For examples of using the `slurm:` prefix, see [this tutorial](../cluster/CLUSTER.md#configure-jobs-with-slurm). |
| `condor:` | Prefix used to specify HTCondor job submission parameters. For example, `condor:bid` with value `10` will put a bid of 10 when submitting the job to HTCondor. This prefix is analogous to `slurm:`. |
| `cmd_env_var:` | Prefix used to specify environment variables that should be set before running the experiment command. For example, `cmd_env_var:CUDA_VISIBLE_DEVICES` with value `0` will set `CUDA_VISIBLE_DEVICES=0` in the environment before executing the experiment command. This is useful for controlling environment-specific behavior like GPU selection, library paths, etc. Multiple environment variables can be set by adding multiple columns with this prefix. The environment variables are exported before the command runs and are available to the command and any subprocesses it spawns. |


## Environment variables table
| Environment Variable | Description |
|---------------------|-------------|
| `GAUTH_CREDENTIALS_PATH` | Path to Google authentication credentials file for a service account. If not set, defaults to `~/.config/gauth/service_key.json`. Used for authenticating with Google services like Google Sheets and Google Drive using a service account. E.g., see how to create this file in [this guide](../syncing/SYNC.md#prepare-service-account-for-google-sheets-and-docs). |
| `PROJECT_ROOT_PROVIDED_FOR_STUNED` | Path to the root directory of the project where experiments will be run. Used by the scheduler to locate experiment files and store outputs. Required when running experiments, as shown in the [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md#run-experiment). |
| `STND_DEFAULT_NUM_ATTEMPTS` | Number of retry attempts for failed operations. Defaults to 10 if not set. Used by the retry mechanism to determine how many times to retry a failed operation before giving up. |

