$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }
& $python (Join-Path $PSScriptRoot "doctor.py")
exit $LASTEXITCODE
