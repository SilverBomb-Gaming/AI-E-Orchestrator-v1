Param(
    [string]$PythonExe
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path $scriptDir -Parent

if (-not $PythonExe) {
    $candidate = Join-Path $repoRoot ".venv-2\Scripts\python.exe"
    if (Test-Path $candidate) {
        $PythonExe = $candidate
    }
    else {
        $PythonExe = "python"
    }
}

Push-Location $repoRoot
try {
    $env:PYTHONUNBUFFERED = "1"
    Write-Host "[run_once] Executing orchestrator once..."
    & $PythonExe -m orchestrator.main --once
} finally {
    Pop-Location
}
