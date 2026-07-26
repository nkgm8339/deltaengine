[CmdletBinding()]
param(
    [int]$DockerTimeoutSec = 300,
    [int]$HealthTimeoutSec = 1200
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$baseCompose = Join-Path $projectRoot "docker-compose.yml"
$stage2bCompose = Join-Path $projectRoot "docker-compose.stage2b.yml"
$stage2aCompose = Join-Path $projectRoot "docker-compose.stage2a.yml"
$overrideCompose = if (Test-Path -LiteralPath $stage2bCompose) {
    $stage2bCompose
} else {
    $stage2aCompose
}
$artifactRoot = Join-Path $projectRoot "data_05M\hook_observer\autostart"
[IO.Directory]::CreateDirectory($artifactRoot) | Out-Null
$runId = "{0}-{1}" -f (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmss.fffffffZ"), ([guid]::NewGuid().ToString("N").Substring(0, 8))
$logPath = Join-Path $artifactRoot "resume-$runId.jsonl"
$logStream = [IO.File]::Open($logPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
$logWriter = [IO.StreamWriter]::new($logStream, [Text.UTF8Encoding]::new($false))
$logWriter.AutoFlush = $true

function Write-RunEvent {
    param(
        [Parameter(Mandatory)][string]$Event,
        [hashtable]$Details = @{}
    )
    $row = [ordered]@{
        schema_version = 1
        event = $Event
        recorded_at = (Get-Date).ToUniversalTime().ToString("o")
        run_id = $runId
    }
    foreach ($key in $Details.Keys) {
        $row[$key] = $Details[$key]
    }
    $logWriter.WriteLine(($row | ConvertTo-Json -Compress -Depth 12))
    $logWriter.Flush()
    $logStream.Flush($true)
}

function Invoke-Docker {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & docker @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        throw "docker $($Arguments -join ' ') failed: $($output -join ' ')"
    }
    return $output
}

$createdNew = $false
$mutex = [Threading.Mutex]::new($false, "Global\DeltaEngineHookCaptureStartup", [ref]$createdNew)
$hasMutex = $false
try {
    $hasMutex = $mutex.WaitOne(0)
    if (-not $hasMutex) {
        Write-RunEvent -Event "ALREADY_RUNNING"
        exit 0
    }

    Write-RunEvent -Event "START" -Details @{
        project_root = $projectRoot
        compose_override = $overrideCompose
        user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    }

    $dockerReady = $false
    try {
        & docker info --format "{{.ServerVersion}}" *> $null
        $dockerReady = $LASTEXITCODE -eq 0
    } catch {
        $dockerReady = $false
    }
    if (-not $dockerReady) {
        Write-RunEvent -Event "DOCKER_START_REQUESTED"
        Invoke-Docker -Arguments @("desktop", "start") | Out-Null
    }

    $dockerDeadline = (Get-Date).AddSeconds($DockerTimeoutSec)
    while ((Get-Date) -lt $dockerDeadline) {
        try {
            $serverVersion = (& docker info --format "{{.ServerVersion}}" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $serverVersion) {
                $dockerReady = $true
                Write-RunEvent -Event "DOCKER_READY" -Details @{
                    server_version = ($serverVersion -join "").Trim()
                }
                break
            }
        } catch {
            $dockerReady = $false
        }
        Start-Sleep -Seconds 2
    }
    if (-not $dockerReady) {
        throw "Docker engine did not become ready within $DockerTimeoutSec seconds"
    }

    Push-Location $projectRoot
    try {
        Invoke-Docker -Arguments @(
            "compose", "-p", "deltaengine_05m",
            "-f", $baseCompose,
            "-f", $overrideCompose,
            "up", "-d", "--no-build", "deltaengine_clone"
        ) | Out-Null
    } finally {
        Pop-Location
    }
    Write-RunEvent -Event "COMPOSE_STARTED"

    $healthUri = "http://127.0.0.1:18080/api/health"
    $statsUri = "http://127.0.0.1:18080/api/stats"
    $healthDeadline = (Get-Date).AddSeconds($HealthTimeoutSec)
    $health = $null
    $stats = $null
    while ((Get-Date) -lt $healthDeadline) {
        try {
            $health = Invoke-RestMethod -Uri $healthUri -TimeoutSec 5
            $stats = Invoke-RestMethod -Uri $statsUri -TimeoutSec 5
            if ($health.state -eq "GREEN" -and $stats.hook_capture.campaign_id) {
                break
            }
        } catch {
            $health = $null
            $stats = $null
        }
        Start-Sleep -Seconds 2
    }
    if ($null -eq $health -or $health.state -ne "GREEN" -or $null -eq $stats) {
        throw "DeltaEngine did not reach GREEN with Hook capture within $HealthTimeoutSec seconds"
    }

    foreach ($streamName in @("full", "liquidation")) {
        $stream = $stats.hook_capture.streams.$streamName
        if ($null -eq $stream) {
            continue
        }
        if ($stream.dropped_queue_full -ne 0 -or
            $stream.rejected_disk_low -ne 0 -or
            $null -ne $stream.writer_error) {
            throw "Hook capture stream $streamName failed integrity checks"
        }
    }

    $drive = Get-PSDrive -Name C
    Write-RunEvent -Event "VERIFIED_GREEN" -Details @{
        health = $health.state
        campaign_id = $stats.hook_capture.campaign_id
        full_original_deadline = $stats.hook_capture.full_capture_until
        full_effective_deadline = $stats.hook_capture.full_effective_capture_until
        liquidation_original_deadline = $stats.hook_capture.liquidation_capture_until
        liquidation_effective_deadline = $stats.hook_capture.liquidation_effective_capture_until
        streams = $stats.hook_capture.streams
        c_free_bytes = $drive.Free
    }
    Write-Output $logPath
    exit 0
} catch {
    Write-RunEvent -Event "FAILED" -Details @{
        error_type = $_.Exception.GetType().FullName
        error = $_.Exception.Message
    }
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
} finally {
    if ($hasMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
    $logWriter.Dispose()
    $logStream.Dispose()
}
