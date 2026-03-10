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
    [int]$TimeoutSec = 180
)

$ErrorActionPreference = "Stop"

function Resolve-UnityEditorPath {
    param(
        [string]$OverridePath
    )

    if ($OverridePath) {
        return $OverridePath
    }

    $envPath = [Environment]::GetEnvironmentVariable("UNITY_EDITOR_EXE", "Process")
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
$projectExists = Test-Path $resolvedProject
if (-not $projectExists) {
    throw "Project path not found: $resolvedProject"
}
$resolvedArtifact = Resolve-OrchestratorPath -Path $ArtifactPath
$resolvedLog = Resolve-OrchestratorPath -Path $LogPath
$unityExe = Resolve-UnityEditorPath

if (Test-Path $resolvedArtifact) {
    Remove-Item $resolvedArtifact -Force
}
if (Test-Path $resolvedLog) {
    Remove-Item $resolvedLog -Force
}

Write-Host "[run_unity_boot] Using Unity editor: $unityExe"
Write-Host "[run_unity_boot] Project: $resolvedProject"
Write-Host "[run_unity_boot] Scene: $SceneName"
Write-Host "[run_unity_boot] Artifact: $resolvedArtifact"
Write-Host "[run_unity_boot] Log: $resolvedLog"

[Environment]::SetEnvironmentVariable("BABYLON_CI_SCENE", $SceneName, "Process")
[Environment]::SetEnvironmentVariable("BABYLON_CI_ARTIFACT", $resolvedArtifact, "Process")

$arguments = @(
    "-batchmode",
    "-nographics",
    "-projectPath", $resolvedProject,
    "-executeMethod", "Babylon.CI.BootProbe.Run",
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
    Write-Host "[run_unity_boot] Unity exited with code $exitCode"
    if ($exitCode -ne 0) {
        throw "Unity returned non-zero exit code $exitCode"
    }

    if (-not (Test-Path $resolvedArtifact)) {
        throw "Artifact not found at $resolvedArtifact"
    }

    Write-Host "[run_unity_boot] Artifact present at $resolvedArtifact"
    exit 0
} catch {
    Write-Error $_
    exit 1
} finally {
    [Environment]::SetEnvironmentVariable("BABYLON_CI_SCENE", $null, "Process")
    [Environment]::SetEnvironmentVariable("BABYLON_CI_ARTIFACT", $null, "Process")
}
