param([int]$IntervalSeconds = 300)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$logsRoot = Join-Path $projectRoot 'artifacts\paper-operator'
if ($IntervalSeconds -lt 30) { throw 'Paper cycle interval must be at least 30 seconds.' }
# Resolve credentials exactly as the worker does, including Windows user variables.
# Constructing this client performs no broker request and prints no credentials.
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -c "from frontier.paper_broker import AlpacaPaper; broker = AlpacaPaper(); broker.close()"
    if ($LASTEXITCODE -ne 0) { throw 'Paper credentials are not configured locally.' }
} finally { Pop-Location }
$statusText = & $pythonPath -m frontier.cli --workspace $projectRoot paper-status
if ($LASTEXITCODE -ne 0) { throw 'Unable to read paper operator status.' }
$status = ($statusText -join "`n") | ConvertFrom-Json
if (-not $status.initialized) { throw 'Initialize a dedicated paper account using paper-init first.' }
New-Item -ItemType Directory -Path $logsRoot -Force | Out-Null
$pidPath = Join-Path $logsRoot 'pid.txt'
if (Test-Path -LiteralPath $pidPath) {
    $savedPid = [int](Get-Content -LiteralPath $pidPath -Raw)
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId=$savedPid" -ErrorAction SilentlyContinue
    if ($existing -and $existing.ExecutablePath -eq $pythonPath -and
        $existing.CommandLine -like '*frontier.cli*paper-watch*' -and
        $existing.CommandLine.Contains($projectRoot)) {
        Write-Output "Paper operator is already running (PID $savedPid)."
        exit 0
    }
}
$arguments = @('-u', '-m', 'frontier.cli', '--workspace', ('"' + $projectRoot + '"'),
               'paper-watch', '--interval-seconds', "$IntervalSeconds")
$process = Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logsRoot 'stdout.log') -RedirectStandardError (Join-Path $logsRoot 'stderr.log')
$process.Id | Set-Content -LiteralPath $pidPath
Write-Output "Paper operator started (PID $($process.Id)); inspect Trading desk and artifacts/paper-operator logs. The host must remain awake."
