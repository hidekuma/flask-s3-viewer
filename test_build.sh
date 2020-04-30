#!/bin/bash
rm -rf dist build
pip uninstall flask_s3_viewer -y
python setup.py bdist_wheel
pip install dist/flask_s3_viewer-*.*.*-py3-none-any.whl
