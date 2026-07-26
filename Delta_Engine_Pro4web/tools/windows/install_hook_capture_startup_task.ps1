#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$TaskName = "DeltaEngineHookCaptureStartup"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$resumeScript = (Resolve-Path (Join-Path $PSScriptRoot "resume_hook_capture.ps1")).Path
$powerShellPath = (Get-Command powershell.exe).Source
$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name

$arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $resumeScript
$action = New-ScheduledTaskAction `
    -Execute $powerShellPath `
    -Argument $arguments `
    -WorkingDirectory $projectRoot

$startupTrigger = New-ScheduledTaskTrigger -AtStartup
$startupTrigger.Delay = "PT30S"
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn -User $currentIdentity
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentIdentity `
    -LogonType S4U `
    -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 2) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

$task = New-ScheduledTask `
    -Action $action `
    -Trigger @($startupTrigger, $logonTrigger) `
    -Principal $principal `
    -Settings $settings `
    -Description "Starts Docker Desktop and resumes the DeltaEngine Hook capture after Windows boot."

Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
$registered = Get-ScheduledTask -TaskName $TaskName

[pscustomobject]@{
    installed_at = (Get-Date).ToString("o")
    task_name = $registered.TaskName
    task_path = $registered.TaskPath
    state = $registered.State.ToString()
    principal_user = $registered.Principal.UserId
    logon_type = $registered.Principal.LogonType.ToString()
    run_level = $registered.Principal.RunLevel.ToString()
    action = $registered.Actions.Execute
    arguments = $registered.Actions.Arguments
    triggers = @($registered.Triggers | ForEach-Object {
        [pscustomobject]@{
            type = $_.CimClass.CimClassName
            enabled = $_.Enabled
            start_boundary = $_.StartBoundary
            delay = $_.Delay
        }
    })
} | ConvertTo-Json -Depth 6
