param([int]$Port = 8765, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendPath = Join-Path $projectRoot 'frontend'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Python environment missing. From this folder run: uv sync --frozen. Then launch Frontier again.'
}
if (-not (Test-Path -LiteralPath (Join-Path $frontendPath 'dist\index.html'))) {
    $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if (-not $npmCommand) { throw 'Node/npm is missing. Install a local Node.js LTS toolchain, then run npm --prefix frontend ci and npm --prefix frontend run build.' }
    & $npmCommand.Source --prefix $frontendPath ci --cache (Join-Path $projectRoot '.cache\npm') --prefer-offline --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed. Review the npm error above and retry npm --prefix frontend ci.' }
    & $npmCommand.Source --prefix $frontendPath run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed. Run npm --prefix frontend run build and review the error.' }
}
$baseUrl = "http://127.0.0.1:$Port"
function Get-FrontierStatus {
    try { return Invoke-RestMethod -Uri "$baseUrl/api/status" -TimeoutSec 2 } catch { return $null }
}
$currentStatus = Get-FrontierStatus
if ($currentStatus -and ($currentStatus.service -ne 'frontier-research' -or $currentStatus.workspace -ne $projectRoot)) {
    throw "Port $Port belongs to a different service or workspace. Run scripts/start.ps1 -Port 8766."
}
if (-not $currentStatus) {
    $logsRoot = Join-Path $projectRoot 'artifacts\service'
    New-Item -ItemType Directory -Path $logsRoot -Force | Out-Null
    # Double-quoted native arguments preserve spaces and apostrophes without a shell.
    $serverArguments = @('-m', 'frontier.cli', '--workspace', ('"' + $projectRoot + '"'), 'serve', '--port', "$Port")
    $serverProcess = Start-Process -FilePath $pythonPath -ArgumentList $serverArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logsRoot 'stdout.log') -RedirectStandardError (Join-Path $logsRoot 'stderr.log')
    $deadline = (Get-Date).AddSeconds(60)
    do {
        Start-Sleep -Milliseconds 400
        $currentStatus = Get-FrontierStatus
        if ($currentStatus) { break }
        if ($serverProcess.HasExited) { throw "Frontier exited. Read artifacts/service/stderr.log, or run .venv\Scripts\python.exe -m frontier.cli doctor." }
    } while ((Get-Date) -lt $deadline)
    if (-not $currentStatus) { throw "Frontier did not become ready at $baseUrl. Read artifacts/service/stderr.log." }
    if ($currentStatus.service -ne 'frontier-research' -or $currentStatus.workspace -ne $projectRoot) { throw "Unexpected service at $baseUrl. Browser was not opened." }
    $serverProcess.Id | Set-Content -LiteralPath (Join-Path $logsRoot 'pid.txt')
}
if (-not $NoBrowser) { Start-Process $baseUrl }
Write-Output "Frontier Research ready at $baseUrl"
