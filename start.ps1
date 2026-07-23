<#
  DeltaEngine 1M — self-contained launcher for a fresh clone.

  Unlike archive/maintenance-scripts/DeltaEngine1M-Manager.ps1 (which assumes the
  parent-folder layout deltaengine/Delta_Engine_Pro4web), this script runs the app
  directly from the repository root it lives in, so a bare `git clone` + this file
  is enough to start the 1M product on http://127.0.0.1:8080.

  Prerequisites (see RESTORE.md): Python 3.12 installed and
  `pip install -r requirements.txt` already run.
#>
param([int]$Port = 8080)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot

# Public venue TLS on Windows: drop any inherited proxy so direct connections work.
foreach ($p in @('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy')) {
    Remove-Item -LiteralPath ('Env:' + $p) -ErrorAction SilentlyContinue
}

$python = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
Write-Host "DeltaEngine 1M starting on http://127.0.0.1:$Port (Ctrl+C to stop)"
Start-Process "http://127.0.0.1:$Port"

& $python -m uvicorn webapp.main:app --app-dir $Root --host 127.0.0.1 --port $Port
