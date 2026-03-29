#!/bin/bash

# Change to the script's directory
cd "$(dirname "$0")"

# Define paths (Linux-style)
BUILD_DIR="build/mewgenics_manager"
DIST_ROOT="dist"
APP_EXE_OUT="$DIST_ROOT/MewgenicsManager"
OS_SUFFIX="linux"
VERSION="$(tr -d '\r\n' < VERSION)"
if [ -z "$VERSION" ]; then
    VERSION="dev"
fi
APP_ZIP_OUT="$DIST_ROOT/MewgenicsManager-$VERSION-$OS_SUFFIX.zip"

echo "Installing / updating dependencies..."
pip install -r requirements.txt
pip install pyinstaller

echo ""
echo "Cleaning previous build output..."
rm -f "$DIST_ROOT"/MewgenicsManager-*.zip
if [ -f "$APP_EXE_OUT" ]; then
    rm -f "$APP_EXE_OUT"
fi
if [ -d "$BUILD_DIR" ]; then
    rm -rf "$BUILD_DIR"
fi

echo ""
echo "Building standalone executable..."
pyinstaller src/mewgenics_manager.spec --noconfirm --distpath "$DIST_ROOT"

echo ""
if [ -f "$APP_EXE_OUT" ]; then
    echo "Build succeeded!"
    echo "Executable: $APP_EXE_OUT"
    echo ""
    echo "Zipping executable..."
    cd "$DIST_ROOT"
    zip -r "MewgenicsManager-$VERSION-$OS_SUFFIX.zip" MewgenicsManager
    cd ..
    if [ -f "$APP_ZIP_OUT" ]; then
        echo "Zip created: $APP_ZIP_OUT"
    else
        echo "Warning: zip creation failed."
    fi
else
    echo "Build FAILED - check output above."
fi
