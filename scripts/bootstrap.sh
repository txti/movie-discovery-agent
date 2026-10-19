#!/bin/bash
set -e

echo "Setting up project..."

# Install uv if not present
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "uv already installed"
fi

# Install dependencies
echo "Installing project dependencies..."
uv sync

echo "Setup complete!"
