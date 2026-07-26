#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$VhdPath = "$env:LOCALAPPDATA\Docker\wsl\disk\docker_data.vhdx"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $VhdPath -PathType Leaf)) {
    throw "Docker VHD was not found: $VhdPath"
}

$dockerProcesses = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -match "^(com\.docker|docker|Docker Desktop)" }
if ($dockerProcesses) {
    $names = ($dockerProcesses.ProcessName | Sort-Object -Unique) -join ", "
    throw "Docker must be fully stopped before compacting the VHD. Running: $names"
}

& wsl.exe --shutdown
if ($LASTEXITCODE -ne 0) {
    throw "wsl --shutdown failed with exit code $LASTEXITCODE"
}
Start-Sleep -Seconds 3

$beforeVhd = Get-Item -LiteralPath $VhdPath
$beforeDrive = Get-PSDrive -Name C

Optimize-VHD -Path $beforeVhd.FullName -Mode Full

$afterVhd = Get-Item -LiteralPath $VhdPath
$afterDrive = Get-PSDrive -Name C

[pscustomobject]@{
    completed_at = (Get-Date).ToString("o")
    vhd_path = $afterVhd.FullName
    vhd_bytes_before = $beforeVhd.Length
    vhd_bytes_after = $afterVhd.Length
    vhd_bytes_reclaimed = $beforeVhd.Length - $afterVhd.Length
    c_free_bytes_before = $beforeDrive.Free
    c_free_bytes_after = $afterDrive.Free
    c_free_bytes_gained = $afterDrive.Free - $beforeDrive.Free
} | ConvertTo-Json -Depth 3
