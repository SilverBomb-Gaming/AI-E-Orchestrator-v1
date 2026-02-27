$workspace = Get-Location
$unityexe = 'd:\program files\unity hub\editor\6000.2.8f1\editor\unity.exe'
if (-not (Test-Path $unityexe)) {
    throw 'unity editor not found at expected path.'
}
$projectpath = 'e:\ai projects 2025\babylon ver 2'
$logdir = Join-Path $workspace 'scripts\logs'
New-Item -ItemType Directory -Force -Path $logdir | Out-Null
$logfile = Join-Path $logdir 'editor.log'
& $unityexe -batchmode -nographics -projectpath $projectpath -logfile $logfile
$waited = 0
while (($waited -lt 30) -and (-not (Test-Path $logfile))) {
    Start-Sleep -Seconds 1
    $waited += 1
}
if (-not (Test-Path $logfile)) {
    throw 'unity did not generate editor.log'
}
