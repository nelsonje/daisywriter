#!/bin/sh
# Pack dist/daisywriter.app (from the PyInstaller spec) into a disk image whose
# window shows the app next to a link to Applications: drag one onto the other.
# Usage: packaging/make_dmg.sh   prints the path of the .dmg it writes
set -eu
cd "$(dirname "$0")/.."
version=$(uv version --short)
out="dist/daisywriter-$version-macos-$(uname -m).dmg"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
ditto dist/daisywriter.app "$stage/daisywriter.app"  # ditto keeps the bundle's links and attributes
ln -s /Applications "$stage/Applications"
rm -f "$out"
hdiutil create -quiet -volname "daisywriter $version" -srcfolder "$stage" -fs HFS+ -format UDZO "$out"
echo "$out"
