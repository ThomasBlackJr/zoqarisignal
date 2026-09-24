param([string]$Python = "")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22.9+ before continuing.' }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if (-not $Python) {
        $installed = Get-Command python -ErrorAction SilentlyContinue
        if ($installed) { $Python = $installed.Source }
        else {
            $bundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
            if (Test-Path -LiteralPath $bundled) { $Python = $bundled }
            else { throw 'Install Python 3.12+, then run .\Setup-Drive.ps1 -Python C:\path\to\python.exe' }
        }
    }
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
}
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
Push-Location frontend
try {
    & npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
} finally { Pop-Location }
if (-not (Test-Path -LiteralPath 'backend\.env')) { Copy-Item -LiteralPath 'backend\.env.example' -Destination 'backend\.env' }
if (-not (Test-Path -LiteralPath 'frontend\.env.local')) { Copy-Item -LiteralPath 'frontend\.env.example' -Destination 'frontend\.env.local' }
Write-Host 'Setup complete. Run .\Start-Signal.ps1 to create your account and start Signal.'
