param(
    [ValidateSet('Start', 'Stop', 'Check')]
    [string]$Action = 'Check'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProductId = 'deltaengine-30m'
$ProjectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\Delta_Engine_30M'))
$RuntimeRoot = Join-Path $ProjectRoot 'runtime'
$WebPort = 8180
$ConfigPath = Join-Path $ProjectRoot 'config\config.yaml'
$LauncherRoot = Join-Path $RuntimeRoot 'launcher'
$PidFile = Join-Path $LauncherRoot 'webapp-30m.pid'
$RequirementsStamp = Join-Path $LauncherRoot 'requirements.sha256'
$RequirementsPath = Join-Path $ProjectRoot 'requirements.txt'
$VenvRoot = Join-Path $ProjectRoot '.venv'
$VenvPython = Join-Path $VenvRoot 'Scripts\python.exe'
$BrowserUrl = "http://127.0.0.1:$WebPort"
$ExpectedDuckDb = Join-Path $RuntimeRoot 'data\duckdb\deltaengine_30m.duckdb'
$ExpectedParquet = Join-Path $RuntimeRoot 'data\parquet'
$ExpectedHfmFile = 'DeltaEngine30M_HFM_quotes_utf8.jsonl'

function Assert-UnderRuntime([string]$PathValue) {
    $full = [System.IO.Path]::GetFullPath($PathValue)
    $runtime = [System.IO.Path]::GetFullPath($RuntimeRoot).TrimEnd('\') + '\'
    if (-not $full.StartsWith($runtime, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "30M mutable path escaped runtime root: $full"
    }
}

function Assert-ProductLayout {
    if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
        throw "30M product root not found: $ProjectRoot"
    }
    if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
        throw "30M config not found: $ConfigPath"
    }
    $config = Get-Content -Raw -LiteralPath $ConfigPath
    if ($config -notmatch '(?m)^\s*duckdb_path:\s*runtime/data/duckdb/deltaengine_30m\.duckdb\s*$') {
        throw '30M DuckDB ownership check failed; refusing startup.'
    }
    if ($config -notmatch '(?m)^\s*parquet_path:\s*runtime/data/parquet\s*$') {
        throw '30M Parquet ownership check failed; refusing startup.'
    }
    if ($config -notmatch '(?m)^\s*log_dir:\s*runtime/data/monitor\s*$') {
        throw '30M monitor ownership check failed; refusing startup.'
    }
    if ($config -notmatch '(?m)^\s*port:\s*8180\s*$') {
        throw '30M WebApp port check failed; refusing startup.'
    }
    if ($config -notmatch '(?m)^\s*port:\s*5655\s*$') {
        throw '30M MT5 adapter port check failed; refusing startup.'
    }
    Assert-UnderRuntime $ExpectedDuckDb
    Assert-UnderRuntime $ExpectedParquet
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

function Ensure-DedicatedEnvironment {
    New-Item -ItemType Directory -Path $LauncherRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        $basePython = (Get-Command python -CommandType Application -ErrorAction Stop).Source
        Write-Host "Creating dedicated 30M virtual environment: $VenvRoot"
        & $basePython -m venv $VenvRoot
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) {
            throw '30M virtual environment creation failed.'
        }
    }

    $requiredHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $RequirementsPath).Hash
    $installedHash = if (Test-Path -LiteralPath $RequirementsStamp) {
        (Get-Content -Raw -LiteralPath $RequirementsStamp).Trim()
    } else { '' }
    if ($installedHash -ne $requiredHash) {
        Write-Host 'Installing dependencies into the dedicated 30M virtual environment...'
        & $VenvPython -m pip install --disable-pip-version-check -r $RequirementsPath
        if ($LASTEXITCODE -ne 0) { throw '30M dependency setup failed.' }
        Set-Content -LiteralPath $RequirementsStamp -Value $requiredHash -Encoding ascii
    }
}

function Show-Check {
    Assert-ProductLayout
    Remove-StalePidFile
    $owned = @(Get-OwnedProcesses)
    $listeners = @(Get-PortListeners)
    [pscustomobject]@{
        Product = $ProductId
        Root = $ProjectRoot
        RuntimeRoot = $RuntimeRoot
        WebPort = $WebPort
        MT5Port = 5655
        DuckDB = $ExpectedDuckDb
        Parquet = $ExpectedParquet
        Python = $VenvPython
        VenvExists = Test-Path -LiteralPath $VenvPython
        HfmCommonFile = $ExpectedHfmFile
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
        Write-Host 'DeltaEngine 30M is not running.'
        return
    }
    foreach ($record in $owned) {
        Write-Host "Stopping DeltaEngine 30M PID $($record.ProcessId)..."
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
        Write-Host "DeltaEngine 30M is already running on $BrowserUrl"
        Start-Process $BrowserUrl
        return
    }

    $listeners = @(Get-PortListeners)
    if ($listeners.Count -gt 0) {
        $details = ($listeners | ForEach-Object { "PID=$($_.OwningProcess)" }) -join ', '
        throw "Port $WebPort is occupied by an unowned process ($details). Nothing was stopped."
    }

    Ensure-DedicatedEnvironment
    $env:DELTAENGINE_PRODUCT = $ProductId
    $arguments = @(
        '-m', 'uvicorn', 'webapp.main:app',
        '--app-dir', $ProjectRoot,
        '--host', '127.0.0.1',
        '--port', [string]$WebPort
    )
    $process = Start-Process -FilePath $VenvPython -ArgumentList $arguments `
        -WorkingDirectory $ProjectRoot -NoNewWindow -PassThru
    Set-Content -LiteralPath $PidFile -Value $process.Id -Encoding ascii
    try {
        Start-Sleep -Seconds 2
        if ($process.HasExited) {
            throw "DeltaEngine 30M exited during startup with code $($process.ExitCode)."
        }
        Start-Process $BrowserUrl
        Write-Host "DeltaEngine 30M started: $BrowserUrl (PID $($process.Id))"
        Write-Host '30M strategy/order logic is not implemented; MT5 order routing remains disabled.'
        Wait-Process -Id $process.Id
        $process.Refresh()
        if ($process.ExitCode -ne 0) {
            throw "DeltaEngine 30M exited with code $($process.ExitCode)."
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
