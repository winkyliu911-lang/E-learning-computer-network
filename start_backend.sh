#!/bin/bash
eval "$(/opt/homebrew/bin/conda "shell.bash" hook)"
conda activate test
cd "/Users/macbook/Desktop/e-learning_sure_multimodel 4/backend"
python app.py
