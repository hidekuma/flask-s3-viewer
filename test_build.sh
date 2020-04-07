#!/bin/bash
rm -rf dist build
pip uninstall flask_s3up -y
python setup.py bdist_wheel
pip install dist/flask_s3up-*.*.*-py3-none-any.whl
