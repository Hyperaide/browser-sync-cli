#!/bin/bash
#
# Build script for HyperAide Browser Sync CLI
#
# This creates a standalone binary with bundled Chromium.
# The binary will be ~250MB but requires no dependencies to run.
#
# Usage:
#   ./build.sh
#
# Output:
#   dist/hyperaide-sync (or hyperaide-sync.exe on Windows)
#

set -e

echo "🔧 HyperAide Browser Sync CLI Builder"
echo "======================================"
echo ""

# Detect platform
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

case "$ARCH" in
    x86_64|amd64)  ARCH="amd64" ;;
    arm64|aarch64) ARCH="arm64" ;;
esac

BINARY_NAME="hyperaide-sync-${OS}-${ARCH}"
echo "Building for: ${OS}/${ARCH}"
echo "Binary name: ${BINARY_NAME}"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not found"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "✓ Using ${PYTHON_VERSION}"

# Install dependencies if needed
echo ""
echo "📦 Installing dependencies..."
pip3 install -q -r requirements.txt
pip3 install -q pyinstaller

# Install Playwright browsers
echo ""
echo "🌐 Installing Chromium browser..."
python3 -m playwright install chromium

# Find Playwright driver location
echo ""
echo "🔍 Locating Playwright driver..."
PLAYWRIGHT_PATH=$(python3 -c "
import playwright
import os
driver_path = os.path.dirname(playwright.__file__)
print(driver_path)
")
echo "   Playwright path: ${PLAYWRIGHT_PATH}"

# Build the binary
echo ""
echo "🏗️  Building binary (this may take a few minutes)..."

pyinstaller \
    --onefile \
    --name "${BINARY_NAME}" \
    --add-data "${PLAYWRIGHT_PATH}/driver:playwright/driver" \
    --hidden-import playwright \
    --hidden-import playwright.sync_api \
    --hidden-import playwright._impl \
    --hidden-import playwright._impl._driver \
    --collect-all playwright \
    --collect-all pyfiglet \
    --hidden-import pyfiglet.fonts \
    --noconfirm \
    --clean \
    main.py

# Check result
if [ -f "dist/${BINARY_NAME}" ]; then
    SIZE=$(du -h "dist/${BINARY_NAME}" | cut -f1)
    echo ""
    echo "✅ Build successful!"
    echo ""
    echo "   Binary: dist/${BINARY_NAME}"
    echo "   Size: ${SIZE}"
    echo ""
    echo "Test it with:"
    echo "   ./dist/${BINARY_NAME} --help"
    echo "   ./dist/${BINARY_NAME} --dev   # Use localhost API"
else
    echo ""
    echo "❌ Build failed - binary not found"
    exit 1
fi
