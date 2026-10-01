$ErrorActionPreference = 'Stop'
$projectRoot = (Get-Location).Path
$probeRoot = Join-Path $projectRoot '.qualification\launch-lifetime'
$child = Start-Process -FilePath (Join-Path $projectRoot '.venv\Scripts\python.exe') -ArgumentList @('-u', ('"' + (Join-Path $probeRoot 'probe.py') + '"')) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $probeRoot 'old.stdout.log') -RedirectStandardError (Join-Path $probeRoot 'old.stderr.log')
Write-Output "Spawned disposable probe PID $($child.Id) at $([DateTime]::UtcNow.ToString('o'))"
