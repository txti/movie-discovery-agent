# Windows bootstrap script
Write-Host "Setting up project..." -ForegroundColor Green

# Check if uv is installed
$uvExists = $null -ne (Get-Command uv -ErrorAction SilentlyContinue)

if (-not $uvExists) {
    Write-Host "Installing uv..." -ForegroundColor Yellow
    powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"
} else {
    Write-Host "✓ uv already installed" -ForegroundColor Green
}

# Install dependencies
Write-Host "Installing project dependencies..." -ForegroundColor Yellow
uv sync

Write-Host "Setup complete!" -ForegroundColor Green
