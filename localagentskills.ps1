$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$installPy = Join-Path $scriptDir "install.py"

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 --version *> $null
    if ($LASTEXITCODE -eq 0) {
        & py -3 $installPy @args
        exit $LASTEXITCODE
    }
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python --version *> $null
    if ($LASTEXITCODE -eq 0) {
        & python $installPy @args
        exit $LASTEXITCODE
    }
}

if (Get-Command python3 -ErrorAction SilentlyContinue) {
    & python3 --version *> $null
    if ($LASTEXITCODE -eq 0) {
        & python3 $installPy @args
        exit $LASTEXITCODE
    }
}

$codexPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path $codexPython) {
    & $codexPython $installPy @args
    exit $LASTEXITCODE
}

Write-Error 'Python 3 was not found. Install Python 3.10+ and enable "Add python.exe to PATH".'
exit 1
