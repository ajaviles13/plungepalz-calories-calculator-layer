#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$(command -v python || command -v python3)}"
"$PYTHON_BIN" -m pytest tests/ -q   # refuse to build on failing tests

rm -rf build plungepalz_calories_layer.zip
mkdir -p build/python
cp -r python/plungepalz_calories build/python/
find build -name '__pycache__' -type d -prune -exec rm -rf {} +
find build -name '*.pyc' -delete
( cd build && zip -qr ../plungepalz_calories_layer.zip python )
rm -rf build

echo "Built plungepalz_calories_layer.zip"
unzip -l plungepalz_calories_layer.zip
