#!/bin/bash
rm -rf dist/ build/ *.egg-info
pip install -e ".[dev,auth]"
python -m build
