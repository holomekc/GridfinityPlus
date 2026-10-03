#!/usr/bin/env bash
# Sets the add-in version in the manifest and packs the add-in into dist/GridfinityPlus-<version>.zip.
# The zip contains a top-level GridfinityPlus/ folder, as Fusion requires the folder name to match the .py file.
set -euo pipefail

version="$1"
name="GridfinityPlus"

sed -i -E "s/(\"version\":[[:space:]]*\")[^\"]*\"/\1${version}\"/" "${name}.manifest"
grep -q "\"${version}\"" "${name}.manifest"

rm -rf dist
mkdir -p "dist/${name}/documentation"
cp -r "${name}.manifest" "${name}.py" config.py LICENSE.md lib commands "dist/${name}/"
cp documentation/PRIVACY_POLICY.md "dist/${name}/documentation/"
find "dist/${name}" -name __pycache__ -type d -prune -exec rm -rf {} +

(cd dist && zip -qr "${name}-${version}.zip" "${name}")
