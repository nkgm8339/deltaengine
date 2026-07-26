[CmdletBinding()]
param(
    [string]$TaskName = "DeltaEngineHookCaptureStartup",
    [string]$ExpectedCampaignId = "stage2a_20260726_xz",
    [string]$PreviousFullSessionId = "",
    [string]$PreviousLiquidationSessionId = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$artifactRoot = Join-Path $projectRoot "data_05M\hook_observer\autostart"
[IO.Directory]::CreateDirectory($artifactRoot) | Out-Null
$artifactId = "{0}-{1}" -f (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmss.fffffffZ"), ([guid]::NewGuid().ToString("N").Substring(0, 8))
$artifactPath = Join-Path $artifactRoot "boot-verification-$artifactId.json"

$os = Get-CimInstance Win32_OperatingSystem
$bootTime = $os.LastBootUpTime
$task = Get-ScheduledTask -TaskName $TaskName
$taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
$health = Invoke-RestMethod -Uri "http://127.0.0.1:18080/api/health" -TimeoutSec 10
$stats = Invoke-RestMethod -Uri "http://127.0.0.1:18080/api/stats" -TimeoutSec 10
$container = (& docker inspect deltaengine_05m-deltaengine_clone-1 | ConvertFrom-Json)[0]

$errors = [Collections.Generic.List[string]]::new()
if ($taskInfo.LastRunTime -le $bootTime) {
    $errors.Add("Scheduled Task did not run after the current boot")
}
if ($taskInfo.LastTaskResult -ne 0) {
    $errors.Add("Scheduled Task result is not zero: $($taskInfo.LastTaskResult)")
}
if ($health.state -ne "GREEN") {
    $errors.Add("DeltaEngine health is not GREEN")
}
if ($stats.hook_capture.campaign_id -ne $ExpectedCampaignId) {
    $errors.Add("Hook campaign ID changed")
}
if (-not $container.State.Running) {
    $errors.Add("DeltaEngine container is not running")
}
if ($PreviousFullSessionId -and
    $stats.hook_capture.streams.full.session_id -eq $PreviousFullSessionId) {
    $errors.Add("Full capture did not create a post-boot session")
}
if ($PreviousLiquidationSessionId -and
    $stats.hook_capture.streams.liquidation.session_id -eq $PreviousLiquidationSessionId) {
    $errors.Add("Liquidation capture did not create a post-boot session")
}
foreach ($streamName in @("full", "liquidation")) {
    $stream = $stats.hook_capture.streams.$streamName
    if ($null -eq $stream) {
        continue
    }
    if ($stream.dropped_queue_full -ne 0) {
        $errors.Add("$streamName queue drop is non-zero")
    }
    if ($stream.rejected_disk_low -ne 0) {
        $errors.Add("$streamName disk rejection is non-zero")
    }
    if ($null -ne $stream.writer_error) {
        $errors.Add("$streamName writer error is present")
    }
}

$result = [ordered]@{
    schema_version = 1
    verified_at = (Get-Date).ToUniversalTime().ToString("o")
    success = $errors.Count -eq 0
    errors = @($errors)
    boot_time = $bootTime.ToUniversalTime().ToString("o")
    task = [ordered]@{
        name = $task.TaskName
        state = $task.State.ToString()
        last_run_time = $taskInfo.LastRunTime.ToUniversalTime().ToString("o")
        last_task_result = $taskInfo.LastTaskResult
    }
    docker = [ordered]@{
        container_id = $container.Id
        image = $container.Config.Image
        image_id = $container.Image
        running = $container.State.Running
        started_at = $container.State.StartedAt
    }
    health = $health
    hook_capture = $stats.hook_capture
    c_free_bytes = (Get-PSDrive C).Free
}

$json = $result | ConvertTo-Json -Depth 15
$bytes = [Text.UTF8Encoding]::new($false).GetBytes($json + "`n")
$stream = [IO.File]::Open($artifactPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::Read)
try {
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush($true)
} finally {
    $stream.Dispose()
}

Write-Output $artifactPath
if ($errors.Count -ne 0) {
    $errors | ForEach-Object { Write-Error $_ }
    exit 1
}
