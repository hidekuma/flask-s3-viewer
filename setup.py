"""Setuptools shim.

Project metadata (PEP 621) and tool configuration live in ``pyproject.toml``.
This file is kept so legacy ``python setup.py``/``pip`` codepaths still work.
"""
from setuptools import setup

setup()
