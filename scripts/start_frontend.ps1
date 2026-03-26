$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..\glass-ui")

if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies..."
    npm install
}

Write-Host "Starting frontend dev server..."
npm run dev