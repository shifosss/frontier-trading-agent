$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $workspaceRoot
$frontierProcesses = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*frontier.cli*' -and $_.CommandLine.Contains($workspaceRoot) })
$webBefore = @($frontierProcesses | Where-Object { $_.CommandLine -match ' serve --port 8765(?:\s|$)' })
$paperBefore = @($frontierProcesses | Where-Object { $_.CommandLine -match ' paper-watch(?:\s|$)' })
$listenerBefore = @(Get-NetTCPConnection -LocalPort 8765 -State Listen)
if ($webBefore.Count -ne 2 -or $paperBefore.Count -ne 2) { throw 'Unexpected worker process tree; no process stopped.' }
if (@($listenerBefore | Where-Object { $_.OwningProcess -notin $webBefore.ProcessId }).Count) { throw 'Listener does not belong to verified web tree.' }
$liveStatus = Invoke-RestMethod 'http://127.0.0.1:8765/api/status' -TimeoutSec 5
if ($liveStatus.service -ne 'frontier-research' -or $liveStatus.workspace -ne $workspaceRoot) { throw 'Unexpected service identity; no process stopped.' }
$before = [ordered]@{ recorded_at=(Get-Date).ToUniversalTime().ToString('o'); web=@($webBefore | Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine); paper=@($paperBefore | Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine); listener=@($listenerBefore | Select-Object LocalAddress,LocalPort,OwningProcess) }
$before | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath '.qualification/web-restart-multi-model-before.json' -Encoding UTF8
foreach ($webProcess in $webBefore) {
    $fresh = Get-CimInstance Win32_Process -Filter "ProcessId=$($webProcess.ProcessId)"
    if ($fresh -and $fresh.CreationDate -eq $webProcess.CreationDate -and $fresh.CommandLine -eq $webProcess.CommandLine) {
        Stop-Process -Id $fresh.ProcessId -Force -ErrorAction Stop
    }
}
$env:PYTHONPATH = Join-Path $workspaceRoot 'src'
& (Join-Path $workspaceRoot 'scripts/start.ps1') -NoBrowser
if ($LASTEXITCODE -ne 0) { throw 'Existing web launcher failed.' }
$schema = Invoke-RestMethod 'http://127.0.0.1:8765/openapi.json' -TimeoutSec 10
$modeSchema = $schema.components.schemas.HistoricalRequest.properties.study_mode
if ($modeSchema.default -ne 'multi_model' -or 'multi_model' -notin $modeSchema.enum) { throw 'New API mode schema not loaded.' }
$frontierAfter = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*frontier.cli*' -and $_.CommandLine.Contains($workspaceRoot) })
$webAfter = @($frontierAfter | Where-Object { $_.CommandLine -match ' serve --port 8765(?:\s|$)' })
$paperAfter = @($frontierAfter | Where-Object { $_.CommandLine -match ' paper-watch(?:\s|$)' })
foreach ($paperProcess in $paperBefore) {
    if (-not @($paperAfter | Where-Object { $_.ProcessId -eq $paperProcess.ProcessId -and $_.CreationDate -eq $paperProcess.CreationDate }).Count) { throw 'Paper process identity changed unexpectedly.' }
}
$after = [ordered]@{ recorded_at=(Get-Date).ToUniversalTime().ToString('o'); web=@($webAfter | Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine); paper=@($paperAfter | Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine); listener=@(Get-NetTCPConnection -LocalPort 8765 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess); study_mode_schema=$modeSchema; paper_processes_unchanged=$true; methods_used=@('GET /api/status','GET /openapi.json'); jobs_launched=0 }
$after | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath '.qualification/web-restart-multi-model-after.json' -Encoding UTF8
$after | ConvertTo-Json -Depth 8
