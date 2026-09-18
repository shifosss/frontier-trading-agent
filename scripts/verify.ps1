$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run uv sync --frozen first.' }
$env:PYTHONIOENCODING = 'utf-8'
& $pythonPath -m ruff check src tests scripts
if ($LASTEXITCODE -ne 0) { throw 'Python lint failed.' }
& $pythonPath -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& npm.cmd --prefix frontend run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend typecheck/build failed.' }
Write-Output 'Verification passed: Python lint, tests, TypeScript and frontend build.'
