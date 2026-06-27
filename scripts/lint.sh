#!/usr/bin/env bash

set -e

cd "$(dirname "$0")/.."

ruff format custom_components tests
ruff check custom_components tests --fix
mypy custom_components/wiser_by_feller/
