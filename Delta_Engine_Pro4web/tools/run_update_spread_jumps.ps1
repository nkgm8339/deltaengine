param(
    [string]$Source = 'data/recordings/btcusdt_board_synced.jsonl'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

python -m tools.update_spread_jumps --source $Source
exit $LASTEXITCODE
