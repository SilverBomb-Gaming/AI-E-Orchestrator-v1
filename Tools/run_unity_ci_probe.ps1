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

    [Parameter(Mandatory = $true)]
    [string]$MethodName,

    [Parameter(Mandatory = $false)]
    [string]$UnityEditorPath,

    [Parameter(Mandatory = $false)]
    [int]$TimeoutSec = 420,

    [Parameter(Mandatory = $false)]
    [int]$MinArtifactBytes = 128
)

$ErrorActionPreference = "Stop"
$script:LauncherTracePath = $null
$script:LauncherTraceSynced = $false

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

function Get-UnityHubEditorCandidates {
    $roots = @(
        "C:\\Program Files\\Unity\\Hub\\Editor",
        "C:\\Program Files\\Unity Hub\\Editor",
        "D:\\Program Files\\Unity\\Hub\\Editor",
        "D:\\Program Files\\Unity Hub\\Editor"
    )
    $candidates = @()
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) {
            continue
        }
        $versions = Get-ChildItem -Path $root -Directory -ErrorAction SilentlyContinue | Sort-Object -Property Name -Descending
        foreach ($version in $versions) {
            $candidate = Join-Path $version.FullName "Editor\\Unity.exe"
            if (Test-Path $candidate) {
                $candidates += $candidate
            }
        }
    }
    return $candidates
}

function Resolve-UnityEditorPath {
    param(
        [string]$OverridePath,
        [string]$ProjectRoot
    )

    if ($OverridePath) {
        if (-not (Test-Path $OverridePath)) {
            throw "Unity editor override path not found: $OverridePath"
        }
        return [System.IO.Path]::GetFullPath($OverridePath)
    }

    $candidates = @()
    foreach ($scope in @("Process", "User", "Machine")) {
        $envPath = [Environment]::GetEnvironmentVariable("UNITY_EDITOR_EXE", $scope)
        if ($envPath) {
            $candidates += $envPath
        }
    }

    $scriptRoot = $PSScriptRoot
    if (-not $scriptRoot) {
        $scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $pathFile = Join-Path $scriptRoot "unity_editor_path.txt"
    if (Test-Path $pathFile) {
        $candidate = (Get-Content $pathFile -ErrorAction Stop | Select-Object -First 1).Trim()
        if ($candidate) {
            $candidates += $candidate
        }
    }

    $candidates += Get-UnityHubEditorCandidates
    $candidates += "D:\\Program Files\\Unity Hub\\Editor\\6000.2.8f1\\Editor\\Unity.exe"

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    $stubCandidates = @()
    if ($ProjectRoot) {
        $stubCandidates += Join-Path $ProjectRoot "Tools\\unity_editor_stub.ps1"
        $stubCandidates += Join-Path $ProjectRoot "Tools\\unity_editor_stub.cmd"
    }
    if ($scriptRoot) {
        $stubCandidates += Join-Path $scriptRoot "unity_editor_stub.ps1"
        $stubCandidates += Join-Path $scriptRoot "unity_editor_stub.cmd"
    }
    foreach ($stub in $stubCandidates) {
        if ($stub -and (Test-Path $stub)) {
            Write-LauncherTrace ("UNITY_STUB_PATH={0}" -f $stub)
            Write-LauncherTrace "USING_STUB=true"
            throw "Unity editor stub detected at '$stub'. Set UNITY_EDITOR_EXE to a real Unity.exe." 
        }
    }

    throw "Unable to resolve Unity editor path. Set UNITY_EDITOR_EXE or provide unity_editor_path.txt."
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

function Get-ArtifactMinBytes {
    param(
        [string]$ArtifactPath,
        [int]$RequestedMin
    )

    $requested = [Math]::Max(1, $RequestedMin)
    $extension = [System.IO.Path]::GetExtension($ArtifactPath)
    if (-not $extension) {
        $extension = ""
    }
    $extension = $extension.ToLowerInvariant()
    switch ($extension) {
        '.json' { return [Math]::Max($requested, 200) }
        '.png' { return [Math]::Max($requested, 10000) }
        default { return $requested }
    }
}

function Get-RequiredJsonKeys {
    param([string]$MethodName)

    $baseKeys = @('status', 'scene', 'timestamp')
    switch ($MethodName) {
        'Babylon.CI.ApplyGrenadeThrowProbe.Run' { return $baseKeys + @('inputAction', 'throwers', 'issues') }
        'Babylon.CI.ApplyGrenadeAnimProbe.Run' { return $baseKeys + @('rigs', 'grenadeClips', 'issues') }
        'Babylon.CI.ZombieSpawnAudit.Run' { return $baseKeys + @('spawners', 'areas', 'issues') }
        'Babylon.CI.ZombieDeathFadeProbe.Run' { return $baseKeys + @('enemies', 'issues') }
        'Babylon.CI.EnemyIngestProbe.Run' { return $baseKeys + @('entries', 'issues', 'manifestPath') }
        'Babylon.CI.ApplyEnemyIntegration.Run' { return $baseKeys + @('integrations', 'issues', 'manifestPath') }
        'Babylon.CI.ZombieSpawnScreenshotProbe.Run' { return $baseKeys + @('screenshot', 'previewEntryId', 'manifestPath') }
        default { return $baseKeys }
    }
}

function Validate-JsonArtifact {
    param(
        [object]$JsonObject,
        [string]$SceneName,
        [string]$MethodName
    )

    if (-not $JsonObject) {
        throw "Artifact JSON is empty."
    }

    $requiredKeys = Get-RequiredJsonKeys -MethodName $MethodName
    foreach ($key in $requiredKeys) {
        if (-not ($JsonObject.PSObject.Properties.Name -contains $key)) {
            throw "Artifact JSON missing required field '$key'."
        }
    }

    $status = [string]$JsonObject.status
    if (-not $status) {
        throw "Artifact JSON missing status value."
    }
    if ($status -eq 'error') {
        throw "Artifact JSON reported error status."
    }

    $scene = [string]$JsonObject.scene
    if (-not [string]::Equals($scene, $SceneName, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Artifact scene '$scene' does not match expected scene '$SceneName'."
    }

    $timestamp = [string]$JsonObject.timestamp
    if (-not $timestamp) {
        throw "Artifact missing timestamp."
    }
    [DateTime]::Parse($timestamp) | Out-Null
}

function Sync-LauncherTraceToLog {
    param([string]$LogPath)

    if (-not $LogPath) {
        return
    }

    if (-not ($script:LauncherTracePath -and (Test-Path $script:LauncherTracePath))) {
        return
    }

    if (Test-Path $LogPath) {
        Get-Content $script:LauncherTracePath | Add-Content -Path $LogPath
    } else {
        $logDir = Split-Path -Parent $LogPath
        if ($logDir -and -not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        }
        Copy-Item -Path $script:LauncherTracePath -Destination $LogPath -Force
    }

    $script:LauncherTraceSynced = $true
}

$resolvedProject = [System.IO.Path]::GetFullPath($ProjectPath)
if (-not (Test-Path $resolvedProject)) {
    throw "Project path not found: $resolvedProject"
}

$resolvedArtifact = Resolve-OrchestratorPath -Path $ArtifactPath
$resolvedLog = Resolve-OrchestratorPath -Path $LogPath
$launcherTracePath = "$resolvedLog.launcher.log"
if (Test-Path $launcherTracePath) {
    Remove-Item $launcherTracePath -Force
}
$script:LauncherTracePath = $launcherTracePath

if (Test-Path $resolvedArtifact) {
    Remove-Item $resolvedArtifact -Force
}
if (Test-Path $resolvedLog) {
    Remove-Item $resolvedLog -Force
}
$logDir = Split-Path -Parent $resolvedLog
if ($logDir -and -not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

$unityExe = Resolve-UnityEditorPath -OverridePath $UnityEditorPath -ProjectRoot $resolvedProject
Write-LauncherTrace "UNITY_EXE_RESOLVED=$unityExe"
Write-LauncherTrace "UNITY_EXE_EXISTS=$([bool](Test-Path $unityExe))"
Write-LauncherTrace "PROJECT_PATH_RESOLVED=$resolvedProject"
Write-LauncherTrace "SCENE_NAME=$SceneName"
Write-LauncherTrace "METHOD_NAME=$MethodName"
Write-LauncherTrace "ARTIFACT_PATH=$resolvedArtifact"
Write-LauncherTrace "LOG_PATH=$resolvedLog"
Ensure-RealUnityEditor $unityExe
Write-Host "[run_unity_ci_probe] Using Unity editor: $unityExe"
Write-Host "[run_unity_ci_probe] Scene: $SceneName"
Write-Host "[run_unity_ci_probe] Method: $MethodName"
Write-Host "[run_unity_ci_probe] Artifact: $resolvedArtifact"
Write-Host "[run_unity_ci_probe] Log: $resolvedLog"

$envMap = @{
    "BABYLON_CI_SCENE"    = $SceneName
    "BABYLON_CI_ARTIFACT" = $resolvedArtifact
    "BABYLON_CI_LOG_PATH" = $resolvedLog
}

foreach ($entry in $envMap.GetEnumerator()) {
    [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
}

$arguments = @(
    "-batchmode",
    "-nographics",
    "-projectPath", $resolvedProject,
    "-executeMethod", $MethodName,
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
        try { $process.Kill() } catch { Write-Warning "Unable to kill Unity process after timeout: $_" }
        throw "Unity process exceeded timeout of ${TimeoutSec}s."
    }

    $process.WaitForExit()
    $exitCode = $process.ExitCode
    Write-LauncherTrace "UNITY_EXIT_CODE=$exitCode"
    Write-Host "[run_unity_ci_probe] Unity exited with code $exitCode"

    if (-not (Test-Path $resolvedArtifact)) {
        throw "Artifact not produced at $resolvedArtifact"
    }

    $artifactInfo = Get-Item $resolvedArtifact
    $requiredSize = Get-ArtifactMinBytes -ArtifactPath $resolvedArtifact -RequestedMin $MinArtifactBytes
    if ($artifactInfo.Length -lt $requiredSize) {
        throw "Artifact at $resolvedArtifact is too small ($($artifactInfo.Length) bytes < $requiredSize bytes minimum)"
    }

    try {
        $json = Get-Content $resolvedArtifact -Raw | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "Artifact at $resolvedArtifact is not valid JSON: $_"
    }

    Validate-JsonArtifact -JsonObject $json -SceneName $SceneName -MethodName $MethodName

    Sync-LauncherTraceToLog -LogPath $resolvedLog

    if (-not (Test-Path $resolvedLog)) {
        throw "Log not found at $resolvedLog"
    }

    $logInfo = Get-Item $resolvedLog
    if ($logInfo.Length -le 0) {
        throw "Log at $resolvedLog is empty"
    }

    if (-not (Select-String -Path $resolvedLog -Pattern "UNITY_EXE_RESOLVED=" -SimpleMatch -Quiet)) {
        throw "Log at $resolvedLog is missing UNITY_EXE_RESOLVED trace entries."
    }

    $standardLogDir = Split-Path -Parent $resolvedLog
    if (-not [string]::IsNullOrEmpty($standardLogDir)) {
        $standardLogPath = Join-Path $standardLogDir "Editor.log"
        $sourceFullPath = [System.IO.Path]::GetFullPath($resolvedLog)
        $destinationFullPath = [System.IO.Path]::GetFullPath($standardLogPath)
        if (-not [string]::Equals($destinationFullPath, $sourceFullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            try {
                Copy-Item -Path $sourceFullPath -Destination $destinationFullPath -Force
                Write-LauncherTrace ("UNITY_EDITOR_LOG_SYNCED={0}" -f $destinationFullPath)
            } catch {
                throw "Failed to sync Unity log to ${standardLogPath}: $_"
            }
        }
    }

    if ($exitCode -ne 0) {
        Write-Warning "Unity returned exit code $exitCode, continuing because artifact validation passed."
    }

    Write-Host "[run_unity_ci_probe] Artifact captured ($($artifactInfo.Length) bytes)."
    exit 0
} catch {
    Write-LauncherTrace ("LAUNCHER_EXCEPTION={0}" -f $_)
    Write-Error $_
    exit 1
} finally {
    foreach ($key in $envMap.Keys) {
        [Environment]::SetEnvironmentVariable($key, $null, "Process")
    }
    try {
        if (-not $script:LauncherTraceSynced) {
            Sync-LauncherTraceToLog -LogPath $resolvedLog
        }
    } catch {
        Write-Warning "Unable to append launcher trace to log: $_"
    }
}
