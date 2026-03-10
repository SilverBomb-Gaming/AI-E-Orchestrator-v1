[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectPath,

    [Parameter(Mandatory = $true)]
    [string]$SceneName,

    [Parameter(Mandatory = $true)]
    [string]$OutPng,

    [Parameter(Mandatory = $true)]
    [string]$LogPath,

    [Parameter(Mandatory = $false)]
    [int]$Width = 1280,

    [Parameter(Mandatory = $false)]
    [int]$Height = 720,

    [Parameter(Mandatory = $false)]
    [int]$TimeoutSec = 180,

    [Parameter(Mandatory = $false)]
    [int]$MinScreenshotBytes = 10240
)

$ErrorActionPreference = "Stop"
$script:LauncherTracePath = $null

function Write-LauncherTrace {
    param([string]$Message)
    if ([string]::IsNullOrWhiteSpace($Message)) {
        return
    }
    Write-Output $Message
    if ($script:LauncherTracePath) {
        $timestamp = (Get-Date).ToString("o")
        Add-Content -Path $script:LauncherTracePath -Value ("[{0}] {1}" -f $timestamp, $Message)
    }
}

function Resolve-UnityEditorPath {
    param([string]$OverridePath)

    if ($OverridePath) {
        return $OverridePath
    }

    foreach ($scope in @("Process", "User", "Machine")) {
        $envPath = [Environment]::GetEnvironmentVariable("UNITY_EDITOR_EXE", $scope)
        if ($envPath -and (Test-Path $envPath)) {
            return $envPath
        }
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

function Ensure-RealUnityEditor {
    param([string]$EditorPath)

    if (-not (Test-Path $EditorPath)) {
        throw "Unity editor not found at '$EditorPath'."
    }

    if ($EditorPath -match "unity_editor_stub") {
        Write-LauncherTrace "USING_STUB=true"
        throw "Unity editor stub detected at '$EditorPath'. Set UNITY_EDITOR_EXE to a real Unity.exe."
    }
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

# Helper to preserve spaces/quotes when emitting a single argument string.
function Join-ArgumentList {
    param([string[]]$Values)

    return ($Values | ForEach-Object {
            if ($_ -match '[\s"]') {
                '"{0}"' -f ($_ -replace '"', '\\"')
            } else {
                $_
            }
        }) -join ' '
}

$resolvedProject = [System.IO.Path]::GetFullPath($ProjectPath)
if (-not (Test-Path $resolvedProject)) {
    throw "Project path not found: $resolvedProject"
}
$resolvedOutPng = Resolve-OrchestratorPath -Path $OutPng
$resolvedLog = Resolve-OrchestratorPath -Path $LogPath
$editorLogPath = [System.IO.Path]::GetFullPath((Join-Path $resolvedProject "scripts\logs\Editor.log"))
$defaultOutputRelative = "scripts\logs\mainmenu_proof.png"
$defaultOutputPath = [System.IO.Path]::GetFullPath((Join-Path $resolvedProject $defaultOutputRelative))
$launcherTracePath = "$resolvedLog.launcher.log"
if (Test-Path $launcherTracePath) {
    Remove-Item $launcherTracePath -Force
}
$script:LauncherTracePath = $launcherTracePath
$launcherTraceEntries = @()
if (Test-Path $resolvedOutPng) {
    Remove-Item $resolvedOutPng -Force
}
if (Test-Path $resolvedLog) {
    Remove-Item $resolvedLog -Force
}
if ($defaultOutputPath -and ($defaultOutputPath -ne $resolvedOutPng) -and (Test-Path $defaultOutputPath)) {
    Remove-Item $defaultOutputPath -Force
}

$unityExe = Resolve-UnityEditorPath
$launcherTraceEntries += "UNITY_EXE_RESOLVED=$unityExe"
$launcherTraceEntries += "UNITY_EXE_EXISTS=$([bool](Test-Path $unityExe))"
$launcherTraceEntries += "PROJECT_PATH_RESOLVED=$resolvedProject"
foreach ($trace in $launcherTraceEntries) {
    Write-LauncherTrace $trace
}
Ensure-RealUnityEditor $unityExe
Write-Host "[run_unity_screenshot] Using Unity editor: $unityExe"
Write-Host "[run_unity_screenshot] Project: $resolvedProject"
Write-Host "[run_unity_screenshot] Scene: $SceneName"
Write-Host "[run_unity_screenshot] Output: $resolvedOutPng"
Write-Host "[run_unity_screenshot] Log: $resolvedLog"

$envVariables = @{
    "BABYLON_CI_SCENE"     = $SceneName
    "BABYLON_CI_OUT_PNG"   = $resolvedOutPng
    "BABYLON_CI_WIDTH"     = $Width
    "BABYLON_CI_HEIGHT"    = $Height
    "BABYLON_CI_LOG_PATH"  = $resolvedLog
}

foreach ($envVar in $envVariables.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($envVar.Key, $envVar.Value, "Process")
}

$arguments = @(
    "-batchmode",
    "-nographics",
    "-projectPath", $resolvedProject,
    "-executeMethod", "Babylon.CI.ScreenshotProbe.Run",
    "-logFile", $resolvedLog,
    "-quit"
)

try {
    $argumentString = Join-ArgumentList -Values $arguments
    $process = Start-Process -FilePath $unityExe `
        -ArgumentList $argumentString `
        -WorkingDirectory $resolvedProject `
        -NoNewWindow `
        -PassThru

    $exited = $process.WaitForExit([Math]::Max(1, $TimeoutSec) * 1000)
    if (-not $exited) {
        try {
            $process.Kill()
        } catch {
            Write-Warning "Unable to kill Unity process after timeout: $_"
        }
        throw "Unity process exceeded timeout of ${TimeoutSec}s."
    }

    # Wait once more without a timeout so ExitCode is always populated.
    $process.WaitForExit()

    $exitCode = -1
    try {
        $exitCode = [int]$process.ExitCode
    } catch {
        Write-Warning "Unable to read Unity exit code: $_"
    }
    Write-Host "[run_unity_screenshot] Unity exited with code $exitCode"

    if (-not (Test-Path $resolvedOutPng) -and $defaultOutputPath -and (Test-Path $defaultOutputPath)) {
        try {
            Move-Item -Path $defaultOutputPath -Destination $resolvedOutPng -Force
            Write-Warning "[run_unity_screenshot] Screenshot was emitted to default path '$defaultOutputRelative'. Moved it to requested location."
        } catch {
            Write-Warning "[run_unity_screenshot] Failed to move screenshot from default path: $_"
        }
    }

    $screenshotExists = Test-Path $resolvedOutPng
    if (-not $screenshotExists) {
        if ($exitCode -ne 0) {
            throw "Unity returned exit code $exitCode and no screenshot was produced at $resolvedOutPng"
        }
        throw "Screenshot not found at $resolvedOutPng"
    }

    $length = (Get-Item $resolvedOutPng).Length
    if ($length -lt $MinScreenshotBytes) {
        throw "Screenshot at $resolvedOutPng is too small ($length bytes < $MinScreenshotBytes bytes minimum)"
    }

    if (-not (Test-Path $resolvedLog)) {
        throw "Log not found at $resolvedLog"
    }

    $logLength = (Get-Item $resolvedLog).Length
    if ($logLength -le 0) {
        throw "Log at $resolvedLog is empty"
    }

    foreach ($trace in $launcherTraceEntries) {
        Add-Content -Path $resolvedLog -Value $trace
    }

    if ($editorLogPath -and -not [string]::Equals($editorLogPath, $resolvedLog, [System.StringComparison]::OrdinalIgnoreCase)) {
        $editorLogDir = Split-Path -Parent $editorLogPath
        if ($editorLogDir -and -not (Test-Path $editorLogDir)) {
            New-Item -ItemType Directory -Force -Path $editorLogDir | Out-Null
        }
        Copy-Item -Path $resolvedLog -Destination $editorLogPath -Force
    }

    if ($exitCode -ne 0) {
        Write-Warning "[run_unity_screenshot] Unity returned exit code $exitCode, but screenshot validation passed. Proceeding."
    }

    Write-Host "[run_unity_screenshot] Screenshot captured ($length bytes)."
    exit 0
} catch {
    Write-Error $_
    exit 1
} finally {
    foreach ($envVar in $envVariables.Keys) {
        [Environment]::SetEnvironmentVariable($envVar, $null, "Process")
    }
}
