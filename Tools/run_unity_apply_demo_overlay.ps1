[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath,

    [Parameter(Mandatory = $true)]
    [string]$SceneName,

    [Parameter(Mandatory = $true)]
    [string]$ArtifactPath,

    [Parameter(Mandatory = $true)]
    [string]$LogPath,

    [Parameter(Mandatory = $false)]
    [int]$TimeoutSec = 240
)

$ErrorActionPreference = "Stop"

function Resolve-UnityEditorPath {
    param(
        [string]$OverridePath
    )

    if ($OverridePath) {
        return $OverridePath
    }

    $envPath = $env:UNITY_EDITOR_EXE
    if ($envPath -and (Test-Path $envPath)) {
        return $envPath
    }

    $scriptRoot = $PSScriptRoot
    if (-not $scriptRoot) {
        $scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $pathFile = Join-Path $scriptRoot "unity_editor_path.txt"
    if (Test-Path $pathFile) {
        $filePath = (Get-Content $pathFile -ErrorAction Stop | Select-Object -First 1).Trim()
        if ($filePath -and (Test-Path $filePath)) {
            return $filePath
        }
    }

    $fallback = "D:\\Program Files\\Unity Hub\\Editor\\6000.2.8f1\\Editor\\Unity.exe"
    if (Test-Path $fallback) {
        return $fallback
    }

    throw "Unable to resolve Unity editor path. Set UNITY_EDITOR_EXE or create Tools\\unity_editor_path.txt."
}

function Resolve-OrchestratorPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Path parameter cannot be empty."
    }

    if ([System.IO.Path]::IsPathRooted($Path)) {
        $fullPath = [System.IO.Path]::GetFullPath($Path)
    } else {
        $fullPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Path))
    }

    $directory = Split-Path -Parent $fullPath
    if ($directory -and -not (Test-Path $directory)) {
        New-Item -ItemType Directory -Force -Path $directory | Out-Null
    }

    return $fullPath
}

$resolvedProject = [System.IO.Path]::GetFullPath($ProjectPath)
if (-not (Test-Path $resolvedProject)) {
    throw "Project path not found: $resolvedProject"
}
$resolvedArtifact = Resolve-OrchestratorPath -Path $ArtifactPath
$resolvedLog = Resolve-OrchestratorPath -Path $LogPath
if (Test-Path $resolvedArtifact) {
    Remove-Item $resolvedArtifact -Force
}
if (Test-Path $resolvedLog) {
    Remove-Item $resolvedLog -Force
}

$unityExe = Resolve-UnityEditorPath
Write-Host "[run_unity_apply_demo_overlay] Using Unity editor: $unityExe"
Write-Host "[run_unity_apply_demo_overlay] Project: $resolvedProject"
Write-Host "[run_unity_apply_demo_overlay] Scene: $SceneName"
Write-Host "[run_unity_apply_demo_overlay] Artifact: $resolvedArtifact"
Write-Host "[run_unity_apply_demo_overlay] Log: $resolvedLog"

$envVariables = @{
    "BABYLON_CI_SCENE"     = $SceneName
    "BABYLON_CI_ARTIFACT"  = $resolvedArtifact
    "BABYLON_CI_LOG_PATH"  = $resolvedLog
}

foreach ($envVar in $envVariables.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($envVar.Key, $envVar.Value, "Process")
}

$arguments = @(
    "-batchmode",
    "-nographics",
    "-projectPath", $resolvedProject,
    "-executeMethod", "Babylon.CI.ApplyDemoOverlay.Run",
    "-logFile", $resolvedLog,
    "-quit"
)

try {
    $process = Start-Process -FilePath $unityExe -ArgumentList $arguments -PassThru -WindowStyle Hidden
    if (-not $process) {
        throw "Failed to launch Unity process."
    }

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    while (-not $process.HasExited) {
        if ($stopwatch.Elapsed.TotalSeconds -ge $TimeoutSec) {
            try {
                $process.Kill()
            } catch {
                Write-Warning "Unable to kill Unity process after timeout: $_"
            }
            throw "Unity process exceeded timeout of ${TimeoutSec}s."
        }
        Start-Sleep -Seconds 1
    }

    $exitCode = $process.ExitCode
    Write-Host "[run_unity_apply_demo_overlay] Unity exited with code $exitCode"
    if ($exitCode -ne 0) {
        throw "Unity returned non-zero exit code $exitCode"
    }

    if (-not (Test-Path $resolvedArtifact)) {
        throw "Overlay artifact not found at $resolvedArtifact"
    }

    Write-Host "[run_unity_apply_demo_overlay] Overlay artifact created."
    exit 0
} catch {
    Write-Error $_
    exit 1
} finally {
    foreach ($envVar in $envVariables.Keys) {
        [Environment]::SetEnvironmentVariable($envVar, $null, "Process")
    }
}
