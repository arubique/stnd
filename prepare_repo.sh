mkdir -p envs && conda create -y --prefix ./envs/stnd_env python==3.10
conda activate ./envs/stnd_env

pip install -r requirements.txt

pre-commit install

