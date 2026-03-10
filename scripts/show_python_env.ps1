param(
    [string]$ExpectedPython = '.\.venv-2\Scripts\python.exe'
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$expected = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $ExpectedPython))
$resolved = Get-Command python -ErrorAction SilentlyContinue
$resolvedPath = if ($resolved) { [System.IO.Path]::GetFullPath($resolved.Source) } else { '<not found>' }
$resolvedVersion = if ($resolved) { & $resolved.Source --version 2>&1 } else { 'python not found' }
$expectedExists = Test-Path $expected
$expectedVersion = if ($expectedExists) { & $expected --version 2>&1 } else { 'expected interpreter not found' }
$shellMatches = $resolvedPath -eq $expected
$status = if ($expectedExists) { 'PASS' } else { 'WARN' }

Write-Output "resolved_python: $resolvedPath"
Write-Output "resolved_python_version: $resolvedVersion"
Write-Output "cwd: $([System.IO.Path]::GetFullPath((Get-Location).Path))"
Write-Output "expected: $expected"
Write-Output "expected_exists: $expectedExists"
Write-Output "expected_python_version: $expectedVersion"
Write-Output "shell_policy_match: $shellMatches"
Write-Output $status

if ($status -eq 'PASS') {
    exit 0
}

exit 1
