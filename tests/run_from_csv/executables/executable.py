import random
import sys
import os


# local imports
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(__file__)),
)
from test_main import STND_ROOT

sys.path.pop(0)

sys.path.insert(
    0,
    STND_ROOT,
)
from stnd.utility.helpers_for_main import prepare_wrapper_for_experiment
from stnd.utility.logger import (
    try_to_log_in_wandb,
    try_to_log_in_csv,
)

sys.path.pop(0)


def check_config_for_demo_experiment(config, config_path, logger):
    assert "initialization_type" in config
    assert "image" in config


def demo_experiment(
    experiment_config, logger, processes_to_kill_before_exiting
):
    image_size = experiment_config["image"]["shape"]

    colored_image = [
        [0 for _ in range(image_size[1])] for _ in range(image_size[0])
    ]
    colored_image = [colored_image for _ in range(3)]

    if experiment_config["image"]["color"] == "red":
        channel = 0
    else:
        channel = 2

    init_type = experiment_config["initialization_type"]

    for i in range(10):
        if init_type == "random":
            colored_image[channel] = [
                [random.random() for _ in range(image_size[1])]
                for _ in range(image_size[0])
            ]
        elif init_type == "zeros":
            colored_image[channel] = [
                [0 for _ in range(image_size[1])] for _ in range(image_size[0])
            ]
        else:
            assert init_type == "ones"
            colored_image[channel] = [
                [1 for _ in range(image_size[1])] for _ in range(image_size[0])
            ]

        mean = sum(
            sum(sum(row) for row in channel) for channel in colored_image
        ) / (image_size[0] * image_size[1] * 3)

        # wandb_stats_to_log = {
        #     "Confusing sample before optimization":
        #     wandb.Image(
        #         colored_image,
        #         caption=
        #             f"Initialization type: {init_type}"
        #     ),
        #     "mean": mean
        # }

        # # log image + mean in wandb
        # try_to_log_in_wandb(
        #     logger,
        #     wandb_stats_to_log,
        #     step=i
        # )

        # log latest mean in csv
        try_to_log_in_csv(logger, "mean of latest tensor", mean)


def main():
    prepare_wrapper_for_experiment(check_config_for_demo_experiment)(
        demo_experiment
    )()


if __name__ == "__main__":
    main()
