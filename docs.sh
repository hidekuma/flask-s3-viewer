#!/bin/bash
set -e

VENV=.venv_docs

if [ ! -x "$VENV/bin/sphinx-build" ]; then
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet \
        sphinx==7.4.6 sphinx-rtd-theme==2.0.0 sphinx-sitemap==2.6.0 \
        m2r2==0.3.3.post2 mistune==0.8.4 docutils==0.20.1 "setuptools<81"
    "$VENV/bin/pip" install --quiet -e .
fi

"$VENV/bin/sphinx-build" -M html docs/source docs
