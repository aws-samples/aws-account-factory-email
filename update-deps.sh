#!/bin/bash
# Script to update all requirements.txt files from requirements.in files

echo "Updating main requirements.txt..."
uv pip compile requirements.in -o requirements.txt --python-version 3.13

echo "Updating vendEmail requirements.txt..."
cd src/vendEmail && uv pip compile requirements.in -o requirements.txt --python-version 3.13 && cd ../..

echo "Updating fwdEmail requirements.txt..."
cd src/fwdEmail && uv pip compile requirements.in -o requirements.txt --python-version 3.13 && cd ../..

echo "Updating tests requirements.txt..."
cd tests && uv pip compile requirements.in -o requirements.txt --python-version 3.13 && cd ..

echo "All requirements.txt files updated!"