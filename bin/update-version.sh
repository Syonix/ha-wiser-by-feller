#!/bin/bash

set -o errexit
set -o pipefail

if [ -z "$1" ]; then
  printf "\e[31mError: version environment variable is not set.\e[0m\n" >&2
  exit 1
fi

# Bump manifest version number
jq '.version = "'"$1"'"' custom_components/wiser_by_feller/manifest.json > tmp
mv tmp custom_components/wiser_by_feller/manifest.json

# Create / replace dist archive
ROOT_DIR="$(pwd)"
STAGING_DIR="$(mktemp -d)"
ARCHIVE_PATH="dist/wiser_by_feller.zip"

mkdir -p "dist"
rm -rf "$ARCHIVE_PATH"

git archive HEAD custom_components/wiser_by_feller | tar -x -C "$STAGING_DIR"

cd "$STAGING_DIR"
zip -r "$ROOT_DIR/$ARCHIVE_PATH" custom_components

cd - >/dev/null
rm -rf "$STAGING_DIR"
