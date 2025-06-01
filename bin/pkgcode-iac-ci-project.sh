#!/bin/bash

# Default environment variables
DEFAULT_TMP_BUILD_DIR="/tmp/iac-ci-build"
DEFAULT_OUTPUT_ZIP="/tmp/iac-ci.zip"
DEFAULT_OUTPUT_TAR="/tmp/iac-ci.tar.gz"

# Use environment variables if set, otherwise use defaults
TMP_BUILD_DIR=${TMP_BUILD_DIR:-$DEFAULT_TMP_BUILD_DIR}
OUTPUT_ZIP=${OUTPUT_ZIP:-$DEFAULT_OUTPUT_ZIP}
OUTPUT_TAR=${OUTPUT_TAR:-$DEFAULT_OUTPUT_TAR}

# Clean up any existing build directory
rm -rf "$TMP_BUILD_DIR"
mkdir -p "$TMP_BUILD_DIR" || { echo "Failed to create build directory"; exit 9; }

# Extract base artifacts
cd ../artifacts || { echo "Failed to change to artifacts directory"; exit 9; }
unzip base.iac-ci-system-lambda.zip -d "$TMP_BUILD_DIR" || { echo "Failed to unzip base artifacts"; exit 9; }

# Copy source files
cd .. || { echo "Failed to change directory"; exit 9; }
cp -rp src/* "$TMP_BUILD_DIR/" || { echo "Failed to copy source files"; exit 9; }

# Clean up any existing output files
rm -rf "$OUTPUT_ZIP" "$OUTPUT_TAR"

# Create archives
cd "$TMP_BUILD_DIR" || { echo "Failed to change to build directory"; exit 9; }
zip -r "$OUTPUT_ZIP" . || { echo "Failed to create zip archive"; exit 9; }
tar cvfz "$OUTPUT_TAR" . || { echo "Failed to create tar archive"; exit 9; }

# Clean up build directory
cd .. || { echo "Failed to change directory"; exit 9; }
rm -rf "$TMP_BUILD_DIR" || { echo "Failed to clean up build directory"; exit 9; }

echo "Build completed successfully"
echo "Output files: $OUTPUT_ZIP, $OUTPUT_TAR"