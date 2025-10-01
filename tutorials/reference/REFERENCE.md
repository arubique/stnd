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

## Environment variables table
| Environment Variable | Description |
|---------------------|-------------|
| `GAUTH_CREDENTIALS_PATH` | Path to Google authentication credentials file. If not set, defaults to `~/.config/gauth/credentials.json`. Used for authenticating with Google services like Google Sheets and Google Drive. E.g., see how to create this file in [this guide](../syncing/SYNC.md#prepare-service-account-for-google-sheets-and-docs). |
| `PROJECT_ROOT_PROVIDED_FOR_STUNED` | Path to the root directory of the project where experiments will be run. Used by the scheduler to locate experiment files and store outputs. Required when running experiments, as shown in the [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md#run-experiment). |

