$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$drivePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $drivePython) -or -not (Test-Path -LiteralPath 'frontend\node_modules')) {
    throw 'Run .\Setup-Drive.ps1 first.'
}
foreach ($drivePort in @(8000, 3000)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $drivePort -ErrorAction SilentlyContinue) {
        throw "Port $drivePort is in use. Stop the existing server before starting Signal."
    }
}
if (-not (Test-Path -LiteralPath 'backend\.env')) { Copy-Item -LiteralPath 'backend\.env.example' -Destination 'backend\.env' }
if (-not (Test-Path -LiteralPath 'frontend\.env.local')) { Copy-Item -LiteralPath 'frontend\.env.example' -Destination 'frontend\.env.local' }
Push-Location backend
try {
    & $drivePython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed. Check backend/.env.' }
    Write-Host 'Create new accounts in the browser. Local verification links are in backend/data/mail-outbox when MAIL_DELIVERY=local.'
} finally { Pop-Location }
$null = New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'backend\data')
$driveBackend = Start-Process -FilePath $drivePython -ArgumentList '-m','uvicorn','app.main:create_app','--factory','--host','127.0.0.1','--port','8000' -WorkingDirectory (Join-Path $PSScriptRoot 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'backend\data\backend.log') -RedirectStandardError (Join-Path $PSScriptRoot 'backend\data\backend-error.log')
try {
    $driveReady = $false
    for ($driveAttempt = 0; $driveAttempt -lt 30; $driveAttempt++) {
        try { $null = Invoke-RestMethod 'http://127.0.0.1:8000/health'; $driveReady = $true; break } catch { Start-Sleep -Milliseconds 500 }
        if ($driveBackend.HasExited) { throw 'Backend startup failed. See backend/data/backend-error.log.' }
    }
    if (-not $driveReady) { throw 'Backend did not become ready. See backend/data/backend-error.log.' }
    Write-Host 'Open http://localhost:3000. Press Ctrl+C here to stop Signal.'
    Push-Location frontend
    try { & npm.cmd run dev } finally { Pop-Location }
} finally {
    if (-not $driveBackend.HasExited) { Stop-Process -Id $driveBackend.Id }
}

