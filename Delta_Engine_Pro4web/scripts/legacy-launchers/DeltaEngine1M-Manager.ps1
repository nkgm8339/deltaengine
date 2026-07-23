param(
    [ValidateSet('Start', 'Stop', 'Check')]
    [string]$Action = 'Check'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProductId = 'deltaengine-1m'
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\Delta_Engine_Pro4web'))
$WebPort = 8080
$ConfigPath = Join-Path $ProjectRoot 'config\config.yaml'
$LauncherRoot = Join-Path $ProjectRoot 'logs\launcher'
$PidFile = Join-Path $LauncherRoot 'webapp-1m.pid'
$SetupMarker = Join-Path $ProjectRoot '.setup_done'
$RequirementsPath = Join-Path $ProjectRoot 'requirements.txt'
$BrowserUrl = "http://127.0.0.1:$WebPort"

function Assert-ProductLayout {
    if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
        throw "1M product root not found: $ProjectRoot"
    }
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw "1M config not found: $ConfigPath"
    }
    $config = Get-Content -Raw -LiteralPath $ConfigPath
    if ($config -notmatch '(?m)^\s*duckdb_path:\s*data/duckdb/orderflow\.duckdb\s*$') {
        throw '1M DuckDB ownership check failed; refusing startup.'
    }
    if ($config -notmatch '(?m)^\s*parquet_path:\s*data/parquet\s*$') {
        throw '1M Parquet ownership check failed; refusing startup.'
    }
}

function Get-CimProcessById([int]$ProcessId) {
    Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
}

function Test-OwnedProcess($ProcessRecord) {
    if ($null -eq $ProcessRecord) { return $false }
    $command = [string]$ProcessRecord.CommandLine
    if ([string]::IsNullOrWhiteSpace($command)) { return $false }
    $normalizedCommand = ($command -replace '/', '\').ToLowerInvariant()
    $normalizedRoot = ($ProjectRoot -replace '/', '\').ToLowerInvariant()
    $portPattern = '(?i)--port\s+"?{0}"?(?:\s|$)' -f $WebPort
    return (
        $normalizedCommand.Contains('uvicorn') -and
        $normalizedCommand.Contains('--app-dir') -and
        $normalizedCommand.Contains($normalizedRoot) -and
        $command -match $portPattern
    )
}

function Get-OwnedProcesses {
    @(
        Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue |
            Where-Object { Test-OwnedProcess $_ }
    )
}

function Get-PortListeners {
    @(Get-NetTCPConnection -State Listen -LocalPort $WebPort -ErrorAction SilentlyContinue)
}

function Remove-StalePidFile {
    if (-not (Test-Path -LiteralPath $PidFile -PathType Leaf)) { return }
    $raw = (Get-Content -Raw -LiteralPath $PidFile).Trim()
    $pidValue = 0
    if ([int]::TryParse($raw, [ref]$pidValue)) {
        $record = Get-CimProcessById $pidValue
        if (Test-OwnedProcess $record) { return }
    }
    Remove-Item -LiteralPath $PidFile -Force
}

function Show-Check {
    Assert-ProductLayout
    Remove-StalePidFile
    $owned = @(Get-OwnedProcesses)
    $listeners = @(Get-PortListeners)
    [pscustomobject]@{
        Product = $ProductId
        Root = $ProjectRoot
        WebPort = $WebPort
        DuckDB = Join-Path $ProjectRoot 'data\duckdb\orderflow.duckdb'
        OwnedProcesses = $owned.Count
        PortListeners = $listeners.Count
        PidFile = $PidFile
    }
}

function Stop-Product {
    Assert-ProductLayout
    Remove-StalePidFile
    $owned = @(Get-OwnedProcesses)
    if ($owned.Count -eq 0) {
        Write-Host 'DeltaEngine 1M is not running.'
        return
    }
    foreach ($record in $owned) {
        Write-Host "Stopping DeltaEngine 1M PID $($record.ProcessId)..."
        Stop-Process -Id $record.ProcessId -ErrorAction Stop
    }
    if (Test-Path -LiteralPath $PidFile) {
        Remove-Item -LiteralPath $PidFile -Force
    }
}

function Start-Product {
    Assert-ProductLayout
    Remove-StalePidFile

    $owned = @(Get-OwnedProcesses)
    if ($owned.Count -gt 0) {
        Write-Host "DeltaEngine 1M is already running on $BrowserUrl"
        Start-Process $BrowserUrl
        return
    }

    $listeners = @(Get-PortListeners)
    if ($listeners.Count -gt 0) {
        $details = ($listeners | ForEach-Object { "PID=$($_.OwningProcess)" }) -join ', '
        throw "Port $WebPort is occupied by an unowned process ($details). Nothing was stopped."
    }

    $python = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    if (-not (Test-Path -LiteralPath $SetupMarker)) {
        Write-Host 'Preparing the existing 1M Python environment...'
        & $python -m pip install -r $RequirementsPath
        if ($LASTEXITCODE -ne 0) { throw '1M dependency setup failed.' }
        Set-Content -LiteralPath $SetupMarker -Value 'done' -Encoding ascii
    }

    New-Item -ItemType Directory -Path $LauncherRoot -Force | Out-Null
    foreach ($proxyName in @('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy')) {
        Remove-Item -LiteralPath ('Env:' + $proxyName) -ErrorAction SilentlyContinue
    }
    $env:DELTAENGINE_PRODUCT = $ProductId
    $arguments = @(
        '-m', 'uvicorn', 'webapp.main:app',
        '--app-dir', $ProjectRoot,
        '--host', '127.0.0.1',
        '--port', [string]$WebPort
    )
    $process = Start-Process -FilePath $python -ArgumentList $arguments `
        -WorkingDirectory $ProjectRoot -NoNewWindow -PassThru
    Set-Content -LiteralPath $PidFile -Value $process.Id -Encoding ascii
    try {
        Start-Sleep -Seconds 2
        if ($process.HasExited) {
            throw "DeltaEngine 1M exited during startup with code $($process.ExitCode)."
        }
        Start-Process $BrowserUrl
        Write-Host "DeltaEngine 1M started: $BrowserUrl (PID $($process.Id))"
        Wait-Process -Id $process.Id
        $process.Refresh()
        if ($process.ExitCode -ne 0) {
            throw "DeltaEngine 1M exited with code $($process.ExitCode)."
        }
    }
    finally {
        if (Test-Path -LiteralPath $PidFile) {
            $current = (Get-Content -Raw -LiteralPath $PidFile).Trim()
            if ($current -eq [string]$process.Id) {
                Remove-Item -LiteralPath $PidFile -Force
            }
        }
    }
}

switch ($Action) {
    'Start' { Start-Product }
    'Stop' { Stop-Product }
    'Check' { Show-Check }
}
