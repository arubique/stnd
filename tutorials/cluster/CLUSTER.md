This tutorial demonstrates how to run experiments on a High Performance Computing (HPC) cluster, for example using the [Slurm](https://slurm.schedmd.com/documentation.html) workload manager.

## Preliminaries

### Be aware of the quick start guide

Before starting this tutorial, make sure you:

- Understand the gist of [Quick Start Guide](../quick_start_guide/QUICK_START_GUIDE.md).
- Have an [Anaconda](https://www.anaconda.com/) environment with the `stnd` package installed as described [here](../../README.md#installation).

## Running experiments

To run experiments on the cluster, simply remove the `--run_locally` flag from the submission command.
For example, the command from [this section](../quick_start_guide/QUICK_START_GUIDE.md#run-experiment) should be modified like this:

```
export ENV=<your env> && export PROJECT_ROOT_PROVIDED_FOR_STUNED=<repo with experiments> && conda activate $ENV && python -m stnd.run_from_csv.__main__ --csv_path $PROJECT_ROOT_PROVIDED_FOR_STUNED/tutorials/quick_start_guide/results.csv --conda_env $ENV
```

The sections below explain how to configure jobs with workload manager-specific commands to specify the amount of resources to allocate for each experiment.

### Configure jobs with Slurm

In the same way we specified config deltas using the `delta:` prefix, we can specify Slurm commands using the `slurm:` prefix.

For example, to submit a job that uses the `gpu` partition, file `/tmp/exp.out` for output and runs for 1 hour, you can pass the corresponding arguments via the results table.
This is done by adding `slurm:partition`, `slurm:output`, `slurm:time`, as shown below (using the example from [here](../quick_start_guide/QUICK_START_GUIDE.md#prepare-results-table)):


| path_to_default_config                                | path_to_main      | whether_to_run | delta:initialization_type | delta:image/color | slurm:output               | slurm:partition | slurm:time |
|-------------------------------------------------------|-------------------|----------------|---------------------------|-------------------|---------------------------|-----------------|------------|
| ./tutorials/quick_start_guide/default_config.yml      | ./experiment.py   | 1              | zeros                     | red               | /tmp/exp.out    | gpu             | 01:00:00   |


Other Slurm-specific commands can be added in the same way using the `slurm:` prefix.
For a full list of available Slurm options and their descriptions, refer to the [Slurm manual](https://slurm.schedmd.com/man_index.html).


