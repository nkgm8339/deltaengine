param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$auditId = 'DE-SEP-001-P0-003'
$audit = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $audit '..\..\..\..')).Path
$oneM = (Resolve-Path (Join-Path $repoRoot 'Delta_Engine_Pro4web')).Path
$thirtyM = (Resolve-Path (Join-Path $repoRoot 'Delta_Engine_30M')).Path
$external = 'I:\マイドライブ\DeltaEngine_Preservation\DE-SEP-001-P0-003'
$manifest = @(Import-Csv -LiteralPath (Join-Path $audit 'PRESERVATION_FILESET_SHA256.csv'))
$activity = @(Import-Csv -LiteralPath (Join-Path $audit 'RUN2_RUNTIME_ACTIVITY_SAMPLE.csv'))
$liveSafe = @(Import-Csv -LiteralPath (Join-Path $audit 'RUN2_LIVE_SAFE_EVIDENCE.csv'))
$derivation = @(Import-Csv -LiteralPath (Join-Path $audit 'DERIVATION_FILE_MAP.csv'))
$hardlinks = @(Import-Csv -LiteralPath (Join-Path $audit 'HARDLINK_INVENTORY.csv'))
$links = @(Import-Csv -LiteralPath (Join-Path $audit 'REPARSE_LINK_INVENTORY.csv'))

function Get-Sha256([string]$path) { return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToUpperInvariant() }
function Git-One([string]$path, [string[]]$gitArgs) {
    $old = Get-Location
    try { Set-Location -LiteralPath $path; $result = @(& git @gitArgs 2>&1); if ($LASTEXITCODE -ne 0) { throw ($result -join "`n") }; return ($result -join "`n") }
    finally { Set-Location $old }
}

$gateReasons = [Collections.Generic.List[string]]::new()
$approvedActive = @(
    'data\execution_costs\quotes_go1_20260723_094459.csv',
    'data\execution_costs\status.json',
    'data\latency\webapp_brushup.stderr.log'
)
foreach ($row in $activity) {
    if ($row.state -in @('CHANGED','ADDED') -and $row.relative_path -notin $approvedActive) { $gateReasons.Add("Unknown active writer/path: $($row.relative_path)") }
    if ($row.state -eq 'REMOVED') { $gateReasons.Add("File removed during activity sample: $($row.relative_path)") }
}
foreach ($row in $liveSafe) { if ($row.pass -ne 'True') { $gateReasons.Add("Live-safe test failed: $($row.relative_path)") } }

$duckRelative = 'data\duckdb\orderflow.duckdb'
$duckInventory = $manifest | Where-Object relative_path -eq $duckRelative | Select-Object -First 1
$duckPath = Join-Path $oneM $duckRelative
$duckCurrentHash = Get-Sha256 $duckPath
if ($duckInventory.sha256 -ne $duckCurrentHash) { $gateReasons.Add('DuckDB changed after Run 2 inventory') }

$pqInventory = @($manifest | Where-Object relative_path -like 'data\parquet\*')
$pqNow = @(Get-ChildItem -LiteralPath (Join-Path $oneM 'data\parquet') -Recurse -Force -File)
$pqInventoryCount = $pqInventory.Count
$pqInventoryBytes = [int64](($pqInventory | Measure-Object size_bytes -Sum).Sum)
$pqInventoryLatest = ($pqInventory.last_write_utc | Sort-Object | Select-Object -Last 1)
$pqNowCount = $pqNow.Count
$pqNowBytes = [int64](($pqNow | Measure-Object Length -Sum).Sum)
$pqNowLatest = ($pqNow.LastWriteTimeUtc | Sort-Object | Select-Object -Last 1).ToString('o')
if ($pqInventoryCount -ne $pqNowCount -or $pqInventoryBytes -ne $pqNowBytes -or $pqInventoryLatest -ne $pqNowLatest) { $gateReasons.Add('Parquet set changed after Run 2 inventory') }

$healthStatus = 'UNAVAILABLE'
$healthError = ''
try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/health' -TimeoutSec 10
    $health | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $audit 'RUN2_HEALTH.json') -Encoding utf8
    if ($null -ne $health.PSObject.Properties['state']) { $healthStatus = [string]$health.state }
    elseif ($null -ne $health.PSObject.Properties['status']) { $healthStatus = [string]$health.status }
} catch {
    $healthError = $_.Exception.Message
    @{ status = 'UNAVAILABLE'; error = $healthError } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $audit 'RUN2_HEALTH.json') -Encoding utf8
}

$pythonVersion = @(& python --version 2>&1) -join ' '
$pythonPath = @(& python -c 'import sys; print(sys.executable)' 2>&1) -join ' '
$freeze = @(& python -m pip freeze --disable-pip-version-check 2>$null | Sort-Object)
[IO.File]::WriteAllLines((Join-Path $audit 'RUN2_PIP_FREEZE.txt'), $freeze, [Text.UTF8Encoding]::new($false))
$pipFreezeHash = Get-Sha256 (Join-Path $audit 'RUN2_PIP_FREEZE.txt')
$requirementsHash = Get-Sha256 (Join-Path $oneM 'requirements.txt')

$resourceRows = @(
    [pscustomobject]@{ resource = '1M_PRODUCT_ROOT'; canonical_path = $oneM; type = 'SOURCE_RUNTIME_ROOT'; owner = '1M'; phase0_action = 'READ_AND_PRESERVE'; status = 'EXISTS' }
    [pscustomobject]@{ resource = '30M_PRODUCT_ROOT'; canonical_path = $thirtyM; type = 'DERIVED_PRODUCT_ROOT'; owner = '30M'; phase0_action = 'READ_ONLY_DERIVATION_MAP'; status = 'EXISTS' }
    [pscustomobject]@{ resource = 'PHASE0_AUDIT_ROOT'; canonical_path = $audit; type = 'AUDIT'; owner = 'SEPARATION'; phase0_action = 'WRITE'; status = 'EXISTS' }
    [pscustomobject]@{ resource = 'EXTERNAL_PRESERVATION_ROOT'; canonical_path = $external; type = 'EXTERNAL_REMOTE_STORAGE'; owner = 'PRESERVATION'; phase0_action = 'WRITE_NEW_ONLY'; status = if (Test-Path -LiteralPath $external) { 'EXISTS' } else { 'MISSING' } }
    [pscustomobject]@{ resource = '1M_HTTP'; canonical_path = 'http://127.0.0.1:8080'; type = 'PROCESS_ENDPOINT'; owner = '1M'; phase0_action = 'READ_HEALTH_ONLY'; status = $healthStatus }
    [pscustomobject]@{ resource = '1M_DUCKDB'; canonical_path = $duckPath; type = 'DATABASE'; owner = '1M'; phase0_action = 'READ_HASH_ONLY_SOURCE'; status = if ($duckInventory.sha256 -eq $duckCurrentHash) { 'STABLE' } else { 'CHANGED' } }
    [pscustomobject]@{ resource = '1M_PARQUET_SET'; canonical_path = (Join-Path $oneM 'data\parquet'); type = 'DATASET'; owner = '1M'; phase0_action = 'READ_HASH_AND_PRESERVE'; status = if ($gateReasons -contains 'Parquet set changed after Run 2 inventory') { 'CHANGED' } else { 'STABLE' } }
)
$resourceRows | Export-Csv -LiteralPath (Join-Path $audit 'ISOLATION_RESOURCE_MATRIX.csv') -NoTypeInformation -Encoding utf8

$outerHead = Git-One $repoRoot @('rev-parse','HEAD')
$outerBranch = Git-One $repoRoot @('branch','--show-current')
$innerHead = Git-One $oneM @('rev-parse','HEAD')
$innerBranch = Git-One $oneM @('branch','--show-current')
$gitlink = Git-One $repoRoot @('ls-files','--stage','--','Delta_Engine_Pro4web')
$innerStatus = @(Get-Content -LiteralPath (Join-Path $audit 'ONE_M_GIT_STATUS_PORCELAIN_V1.txt'))
$tags = @(Git-One $oneM @('show-ref','--tags') -split "`n" | Where-Object { $_ })
$remotes = @(Git-One $oneM @('remote','-v') -split "`n" | Where-Object { $_ })
$classSummary = @($manifest | Group-Object classification | Sort-Object Name | ForEach-Object { [pscustomobject]@{ classification = $_.Name; file_count = $_.Count; bytes = [int64](($_.Group | Measure-Object size_bytes -Sum).Sum) } })
$runtimeSummary = @($manifest | Where-Object classification -eq 'C' | Group-Object runtime_state | Sort-Object Name | ForEach-Object { [pscustomobject]@{ runtime_state = $_.Name; file_count = $_.Count; bytes = [int64](($_.Group | Measure-Object size_bytes -Sum).Sum) } })
$hashErrors = @($manifest | Where-Object hash_status -like 'ERROR:*')
foreach ($row in $hashErrors) { $gateReasons.Add("Hash error: $($row.relative_path)") }

$summary = [ordered]@{
    audit_id = $auditId
    captured_utc = (Get-Date).ToUniversalTime().ToString('o')
    outer_head = $outerHead
    outer_branch = $outerBranch
    gitlink_entry = $gitlink
    inner_head = $innerHead
    inner_branch = $innerBranch
    inner_modified_count = @($innerStatus | Where-Object { $_ -notlike '??*' }).Count
    inner_untracked_count = @($innerStatus | Where-Object { $_ -like '??*' }).Count
    tags = $tags
    remotes = $remotes
    one_m_file_count = $manifest.Count
    one_m_total_bytes = [int64](($manifest | Measure-Object size_bytes -Sum).Sum)
    class_summary = $classSummary
    runtime_summary = $runtimeSummary
    activity_changes = $activity
    hash_error_count = $hashErrors.Count
    reparse_link_count = $links.Count
    hardlink_multiple_count = @($hardlinks | Where-Object { $_.link_count -match '^\d+$' -and [int]$_.link_count -gt 1 }).Count
    duckdb_inventory_hash = $duckInventory.sha256
    duckdb_current_hash = $duckCurrentHash
    duckdb_hash_stable = ($duckInventory.sha256 -eq $duckCurrentHash)
    parquet_inventory = [ordered]@{ count = $pqInventoryCount; bytes = $pqInventoryBytes; latest = $pqInventoryLatest }
    parquet_current = [ordered]@{ count = $pqNowCount; bytes = $pqNowBytes; latest = $pqNowLatest }
    health_status = $healthStatus
    health_error = $healthError
    python_version = $pythonVersion
    python_executable = $pythonPath
    requirements_sha256 = $requirementsHash
    pip_freeze_sha256 = $pipFreezeHash
    process_count = @(Import-Csv -LiteralPath (Join-Path $audit 'RUN2_PROCESS_SNAPSHOT.csv')).Count
    thirty_m_file_count = $derivation.Count
    gate_0a_r_required = ($gateReasons.Count -gt 0)
    gate_0a_r_reasons = @($gateReasons)
}
$summary | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $audit 'RUN2_REMEASUREMENT.json') -Encoding utf8
Write-Output ("RUN2_REMEASUREMENT_FINALIZED gate_0a_r_required={0} files={1} runtime={2} active={3}" -f ($gateReasons.Count -gt 0), $manifest.Count, @($manifest | Where-Object classification -eq 'C').Count, @($manifest | Where-Object runtime_state -eq 'ACTIVE_RUNTIME').Count)
