param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$auditId = 'DE-SEP-001-P0-004'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..\..')).Path
$oneM = (Resolve-Path (Join-Path $repoRoot 'Delta_Engine_Pro4web')).Path
$thirtyM = (Resolve-Path (Join-Path $repoRoot 'Delta_Engine_30M')).Path
$audit = $PSScriptRoot
$external = 'I:\マイドライブ\DeltaEngine_Preservation\DE-SEP-001-P0-004'
$capturedUtc = (Get-Date).ToUniversalTime().ToString('o')

function Get-RelativePath([string]$root, [string]$path) {
    return [IO.Path]::GetRelativePath($root, $path).Replace('/', '\')
}

function Get-Sha256([string]$path) {
    return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Get-Classification([string]$relativePath) {
    $segments = $relativePath -split '\\'
    if (@($segments | Where-Object {
            $_ -eq '__pycache__' -or
            $_ -eq '.pytest_cache' -or
            $_ -eq '.pytest_tmp' -or
            $_ -like '.pytest-*' -or
            $_ -in @('latency_test_tmp', 'test_tmp', 'tmp_pytest_run')
        }).Count -gt 0 -or
        $relativePath.EndsWith('.pyc', [StringComparison]::OrdinalIgnoreCase)) {
        return [pscustomobject]@{ Class = 'E'; Reason = 'regenerable Python/pytest cache or temporary test artifact' }
    }
    if ($relativePath -eq '.setup_done' -or $relativePath.StartsWith('data\', [StringComparison]::OrdinalIgnoreCase)) {
        return [pscustomobject]@{ Class = 'C'; Reason = 'runtime, database, market data, recording, report, or state artifact' }
    }
    if ($relativePath -in @('.gitignore', 'docker-compose.yml', 'Dockerfile')) {
        return [pscustomobject]@{ Class = 'D'; Reason = 'operational/build metadata required for forensic reconstruction' }
    }
    if ($relativePath.StartsWith('tools\', [StringComparison]::OrdinalIgnoreCase) -or
        $relativePath.StartsWith('tests\tools\', [StringComparison]::OrdinalIgnoreCase) -or
        $relativePath -in @(
            'config\execution_costs.yaml',
            'config\flow_strategy_evaluation.yaml',
            'LATENCY_OBSERVER.md',
            'requirements.txt',
            'STRATEGY_EVALUATION.md',
            'mt5\HFMQuoteObserver.ex5',
            'mt5\HFMQuoteObserver.mq5'
        )) {
        return [pscustomobject]@{ Class = 'B'; Reason = 'research, observer, calibration, evaluation, or supporting analysis artifact' }
    }
    return [pscustomobject]@{ Class = 'A'; Reason = 'core 1M application, test, configuration, asset, or project documentation' }
}

function Get-FileSnapshot([string]$root) {
    $enumErrors = @()
    $items = @(Get-ChildItem -LiteralPath $root -Recurse -Force -File -ErrorAction SilentlyContinue -ErrorVariable +enumErrors |
        Where-Object { -not (Get-RelativePath $root $_.FullName).StartsWith('.git\', [StringComparison]::OrdinalIgnoreCase) })
    $rows = foreach ($item in $items) {
        [pscustomobject]@{
            relative_path = Get-RelativePath $root $item.FullName
            full_path = $item.FullName
            size_bytes = [int64]$item.Length
            last_write_utc = $item.LastWriteTimeUtc.ToString('o')
            attributes = $item.Attributes.ToString()
            link_type = if ($null -eq $item.LinkType) { '' } else { [string]$item.LinkType }
            link_target = if ($null -eq $item.Target) { '' } else { [string]::Join('|', @($item.Target)) }
        }
    }
    return [pscustomobject]@{ Rows = @($rows | Sort-Object relative_path); Errors = @($enumErrors | ForEach-Object { $_.Exception.Message } | Sort-Object -Unique) }
}

function Get-PrefixHash([string]$path, [int64]$length) {
    $stream = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            $buffer = New-Object byte[] 1048576
            $remaining = $length
            while ($remaining -gt 0) {
                $take = [int][Math]::Min($buffer.Length, $remaining)
                $read = $stream.Read($buffer, 0, $take)
                if ($read -le 0) { throw "Unexpected EOF for prefix: $path" }
                [void]$sha.TransformBlock($buffer, 0, $read, $null, 0)
                $remaining -= $read
            }
            [void]$sha.TransformFinalBlock([byte[]]::new(0), 0, 0)
            return [Convert]::ToHexString($sha.Hash)
        } finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}

function Test-AppendPrefix([string]$path) {
    $stream = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)
    try {
        $length = $stream.Length
        if ($length -eq 0) {
            $emptyHash = Get-PrefixHash $path 0
            return [pscustomobject]@{
                cutoff_bytes = [int64]0
                prefix_hash_before = $emptyHash
                prefix_hash_after = $emptyHash
                pass = $true
            }
        }
        $tailLength = [int][Math]::Min([int64]1048576, $length)
        $tail = New-Object byte[] $tailLength
        $stream.Seek($length - $tailLength, [IO.SeekOrigin]::Begin) | Out-Null
        $read = $stream.Read($tail, 0, $tailLength)
        $lastLf = -1
        for ($i = $read - 1; $i -ge 0; $i--) { if ($tail[$i] -eq 10) { $lastLf = $i; break } }
        if ($lastLf -lt 0) { throw "No newline boundary found: $path" }
        $cutoff = ($length - $tailLength) + $lastLf + 1
    } finally { $stream.Dispose() }
    $hash1 = Get-PrefixHash $path $cutoff
    Start-Sleep -Seconds 3
    $hash2 = Get-PrefixHash $path $cutoff
    return [pscustomobject]@{ cutoff_bytes = $cutoff; prefix_hash_before = $hash1; prefix_hash_after = $hash2; pass = ($hash1 -eq $hash2) }
}

function Get-GitText([string]$workingDirectory, [string[]]$arguments) {
    $old = Get-Location
    try {
        Set-Location -LiteralPath $workingDirectory
        $result = & git @arguments 2>&1
        if ($LASTEXITCODE -ne 0) { throw "git $($arguments -join ' ') failed: $result" }
        return @($result | ForEach-Object { [string]$_ })
    } finally { Set-Location $old }
}

# Immutable prior evidence is hashed before Run 1 writes continue.
$legacyRows = foreach ($legacyId in @('DE-SEP-001-P0-001', 'DE-SEP-001-P0-002', 'DE-SEP-001-P0-003')) {
    $legacyPath = Join-Path (Split-Path $audit -Parent) $legacyId
    foreach ($file in @(Get-ChildItem -LiteralPath $legacyPath -File -Force | Sort-Object Name)) {
        [pscustomobject]@{
            audit_id = $legacyId
            relative_path = $file.Name
            size_bytes = [int64]$file.Length
            last_write_utc = $file.LastWriteTimeUtc.ToString('o')
            sha256_before_run2 = Get-Sha256 $file.FullName
        }
    }
}
$legacyRows | Export-Csv -LiteralPath (Join-Path $audit 'LEGACY_AUDIT_INTEGRITY_PRE.csv') -NoTypeInformation -Encoding utf8

# Git evidence.
$outerHead = (Get-GitText $repoRoot @('rev-parse', 'HEAD'))[0]
$outerBranch = (Get-GitText $repoRoot @('branch', '--show-current'))[0]
$outerStatus = Get-GitText $repoRoot @('status', '--porcelain=v1', '--untracked-files=all')
[IO.File]::WriteAllLines((Join-Path $audit 'OUTER_GIT_STATUS_PORCELAIN_V1.txt'), $outerStatus, [Text.UTF8Encoding]::new($false))
$innerHead = (Get-GitText $oneM @('rev-parse', 'HEAD'))[0]
$innerBranch = (Get-GitText $oneM @('branch', '--show-current'))[0]
$innerStatus = Get-GitText $oneM @('status', '--porcelain=v1', '--untracked-files=all')
[IO.File]::WriteAllLines((Join-Path $audit 'ONE_M_GIT_STATUS_PORCELAIN_V1.txt'), $innerStatus, [Text.UTF8Encoding]::new($false))
$dirtyPatch = Get-GitText $oneM @('diff', '--binary', '--full-index', 'HEAD')
[IO.File]::WriteAllLines((Join-Path $audit 'ONE_M_DIRTY_PATCH.diff'), $dirtyPatch, [Text.UTF8Encoding]::new($false))
$tracked = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($line in (Get-GitText $oneM @('ls-files'))) { [void]$tracked.Add($line.Replace('/', '\')) }
$statusMap = @{}
foreach ($line in $innerStatus) {
    if ($line.Length -ge 4) {
        $status = $line.Substring(0, 2)
        $path = $line.Substring(3).Trim('"').Replace('/', '\')
        $statusMap[$path] = $status
    }
}
$tags = Get-GitText $oneM @('show-ref', '--tags')
$remotes = Get-GitText $oneM @('remote', '-v')
$gitlink = (Get-GitText $repoRoot @('ls-files', '--stage', '--', 'Delta_Engine_Pro4web')) -join ''

# Full 1M inventory and fresh hashes.
$snap1 = Get-FileSnapshot $oneM
$hashRows = [Collections.Generic.List[object]]::new()
foreach ($row in $snap1.Rows) {
    $class = Get-Classification $row.relative_path
    $hash = ''
    $hashStatus = 'OK'
    try { $hash = Get-Sha256 $row.full_path } catch { $hashStatus = 'ERROR: ' + $_.Exception.Message }
    $gitState = if ($statusMap.ContainsKey($row.relative_path)) { $statusMap[$row.relative_path] } elseif ($tracked.Contains($row.relative_path)) { 'CLEAN' } else { 'IGNORED_OR_GENERATED' }
    $hashRows.Add([pscustomobject]@{
        relative_path = $row.relative_path
        sha256 = $hash
        hash_status = $hashStatus
        git_state = $gitState
        size_bytes = $row.size_bytes
        last_write_utc = $row.last_write_utc
        classification = $class.Class
        classification_reason = $class.Reason
        runtime_state = if ($class.Class -eq 'C') { 'UNMEASURED' } else { 'NOT_RUNTIME' }
    })
}

# Activity sample determines stable versus active C files without stopping processes.
$beforeMap = @{}
foreach ($row in $snap1.Rows) { $beforeMap[$row.relative_path] = "$($row.size_bytes)|$($row.last_write_utc)" }
$duckPath = Join-Path $oneM 'data\duckdb\orderflow.duckdb'
$duckHashBefore = if (Test-Path -LiteralPath $duckPath) { Get-Sha256 $duckPath } else { '' }
Start-Sleep -Seconds 8
$snap2 = Get-FileSnapshot $oneM
$afterMap = @{}
foreach ($row in $snap2.Rows) { $afterMap[$row.relative_path] = "$($row.size_bytes)|$($row.last_write_utc)" }
$activity = [Collections.Generic.List[object]]::new()
foreach ($path in @($beforeMap.Keys + $afterMap.Keys | Sort-Object -Unique)) {
    $state = if (-not $beforeMap.ContainsKey($path)) { 'ADDED' } elseif (-not $afterMap.ContainsKey($path)) { 'REMOVED' } elseif ($beforeMap[$path] -ne $afterMap[$path]) { 'CHANGED' } else { 'UNCHANGED' }
    if ($state -ne 'UNCHANGED') {
        $activity.Add([pscustomobject]@{ relative_path = $path; state = $state; before = if ($beforeMap.ContainsKey($path)) { $beforeMap[$path] } else { '' }; after = if ($afterMap.ContainsKey($path)) { $afterMap[$path] } else { '' } })
    }
}
$activity | Export-Csv -LiteralPath (Join-Path $audit 'RUN1_RUNTIME_ACTIVITY_SAMPLE.csv') -NoTypeInformation -Encoding utf8
$activeSet = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($change in $activity) { if ($change.state -in @('CHANGED', 'ADDED')) { [void]$activeSet.Add($change.relative_path) } }
$knownProcessOwnedPaths = @(
    'data\execution_costs\observer_go1_20260723_094459.stderr.log',
    'data\execution_costs\observer_go1_20260723_094459.stdout.log',
    'data\execution_costs\quotes_go1_20260723_094459.csv',
    'data\execution_costs\status.json',
    'data\latency\webapp_brushup.stderr.log',
    'data\latency\webapp_brushup.stdout.log',
    'data\monitor\anomalies_20260723.jsonl'
)
foreach ($path in $knownProcessOwnedPaths) {
    if (Test-Path -LiteralPath (Join-Path $oneM $path) -PathType Leaf) {
        [void]$activeSet.Add($path)
    }
}
foreach ($row in $hashRows) {
    if ($row.classification -eq 'C') { $row.runtime_state = if ($activeSet.Contains($row.relative_path)) { 'ACTIVE_RUNTIME' } else { 'STABLE_DATA' } }
}
$hashRows | Export-Csv -LiteralPath (Join-Path $audit 'PRESERVATION_FILESET_SHA256.csv') -NoTypeInformation -Encoding utf8
$sourcePre = @($hashRows | Where-Object classification -in @('A', 'B', 'D') | Select-Object relative_path,size_bytes,sha256)
$sourcePre | Export-Csv -LiteralPath (Join-Path $audit 'WORKTREE_CAPTURE_PRE_SHA256.csv') -NoTypeInformation -Encoding utf8

# Reparse/symlink inventory; absence is an explicit PASS result.
$linkRows = @($snap2.Rows | Where-Object { $_.attributes -match 'ReparsePoint' -or $_.link_type -or $_.link_target } |
    Select-Object relative_path,attributes,link_type,link_target)
$linkRows | Export-Csv -LiteralPath (Join-Path $audit 'REPARSE_LINK_INVENTORY.csv') -NoTypeInformation -Encoding utf8

# Targeted hardlink check covers every preserved source file plus DB and active files.
$hardlinkRows = [Collections.Generic.List[object]]::new()
$hardlinkCandidates = @($sourcePre.relative_path + 'data\duckdb\orderflow.duckdb' + @($activeSet) | Sort-Object -Unique)
foreach ($relativePath in $hardlinkCandidates) {
    $fullPath = Join-Path $oneM $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) { continue }
    $lines = @(& fsutil hardlink list $fullPath 2>$null)
    if ($LASTEXITCODE -eq 0) {
        $hardlinkRows.Add([pscustomobject]@{ relative_path = $relativePath; link_count = $lines.Count; links = ($lines -join '|') })
    } else {
        $hardlinkRows.Add([pscustomobject]@{ relative_path = $relativePath; link_count = ''; links = 'FSUTIL_QUERY_FAILED' })
    }
}
$hardlinkRows | Export-Csv -LiteralPath (Join-Path $audit 'HARDLINK_INVENTORY.csv') -NoTypeInformation -Encoding utf8

# Gate 0A-R live-safe checks.
$gateReasons = [Collections.Generic.List[string]]::new()
foreach ($message in @($snap1.Errors + $snap2.Errors | Sort-Object -Unique)) {
    $gateReasons.Add("Incomplete product inventory: $message")
}
foreach ($row in @($hashRows | Where-Object hash_status -ne 'OK')) {
    $gateReasons.Add("Hash failure: $($row.relative_path) - $($row.hash_status)")
}
$activeEvidence = [Collections.Generic.List[object]]::new()
foreach ($path in @($activeSet | Sort-Object)) {
    $fullPath = Join-Path $oneM $path
    if ([IO.Path]::GetExtension($path) -in @('.csv', '.log', '.jsonl')) {
        try {
            $prefix = Test-AppendPrefix $fullPath
            $method = if ($prefix.cutoff_bytes -eq 0) { 'SHARED_READ_ZERO_LENGTH' } else { 'SHARED_READ_FIXED_NEWLINE_PREFIX' }
            $activeEvidence.Add([pscustomobject]@{ relative_path = $path; method = $method; cutoff_bytes = $prefix.cutoff_bytes; hash_before = $prefix.prefix_hash_before; hash_after = $prefix.prefix_hash_after; pass = $prefix.pass; detail = '' })
            if (-not $prefix.pass) { $gateReasons.Add("Unstable prefix: $path") }
        } catch {
            $gateReasons.Add("Shared-read prefix failed: $path - $($_.Exception.Message)")
            $activeEvidence.Add([pscustomobject]@{ relative_path = $path; method = 'SHARED_READ_FIXED_NEWLINE_PREFIX'; cutoff_bytes = ''; hash_before = ''; hash_after = ''; pass = $false; detail = $_.Exception.Message })
        }
    } elseif ($path -eq 'data\execution_costs\status.json') {
        try {
            $bytes = [IO.File]::ReadAllBytes($fullPath)
            $json = [Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json -ErrorAction Stop
            $jsonHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes))
            $activeEvidence.Add([pscustomobject]@{ relative_path = $path; method = 'ATOMIC_JSON_READ'; cutoff_bytes = $bytes.Length; hash_before = $jsonHash; hash_after = $jsonHash; pass = $true; detail = 'JSON_PARSE_PASS' })
        } catch {
            $gateReasons.Add("Atomic JSON read failed: $path - $($_.Exception.Message)")
            $activeEvidence.Add([pscustomobject]@{ relative_path = $path; method = 'ATOMIC_JSON_READ'; cutoff_bytes = ''; hash_before = ''; hash_after = ''; pass = $false; detail = $_.Exception.Message })
        }
    } else {
        $gateReasons.Add("Unknown active writer/path: $path")
        $activeEvidence.Add([pscustomobject]@{ relative_path = $path; method = 'UNAPPROVED'; cutoff_bytes = ''; hash_before = ''; hash_after = ''; pass = $false; detail = 'UNKNOWN_ACTIVE_PATH' })
    }
}
$activeEvidence | Export-Csv -LiteralPath (Join-Path $audit 'RUN1_LIVE_SAFE_EVIDENCE.csv') -NoTypeInformation -Encoding utf8
$duckHashAfter = if (Test-Path -LiteralPath $duckPath) { Get-Sha256 $duckPath } else { '' }
if ($duckHashBefore -ne $duckHashAfter) { $gateReasons.Add('DuckDB changed during Run 1 remeasurement') }
$parquetBefore = @($snap1.Rows | Where-Object relative_path -like 'data\parquet\*')
$parquetAfter = @($snap2.Rows | Where-Object relative_path -like 'data\parquet\*')
$pq1 = [pscustomobject]@{ count = $parquetBefore.Count; bytes = [int64](($parquetBefore | Measure-Object size_bytes -Sum).Sum); latest = ($parquetBefore.last_write_utc | Sort-Object | Select-Object -Last 1) }
$pq2 = [pscustomobject]@{ count = $parquetAfter.Count; bytes = [int64](($parquetAfter | Measure-Object size_bytes -Sum).Sum); latest = ($parquetAfter.last_write_utc | Sort-Object | Select-Object -Last 1) }
if ($pq1.count -ne $pq2.count -or $pq1.bytes -ne $pq2.bytes -or $pq1.latest -ne $pq2.latest) { $gateReasons.Add('Parquet set changed during Run 1 remeasurement') }

# Runtime manifest starts complete and is enriched with archive evidence in the next script.
$runtimeRows = foreach ($row in @($hashRows | Where-Object classification -eq 'C')) {
    [pscustomobject]@{
        relative_path = $row.relative_path
        runtime_state = $row.runtime_state
        source_size_at_inventory = $row.size_bytes
        source_sha256_at_inventory = $row.sha256
        capture_method = if ($row.runtime_state -eq 'STABLE_DATA') {
            'PRE_POST_HASH_AND_PHYSICAL_ZIP'
        } elseif ($row.relative_path -eq 'data\execution_costs\status.json') {
            'ATOMIC_JSON_SNAPSHOT'
        } elseif ($row.size_bytes -eq 0) {
            'SHARED_READ_ZERO_LENGTH'
        } else {
            'SHARED_READ_FIXED_NEWLINE_PREFIX'
        }
        snapshot_size_bytes = ''
        snapshot_sha256 = ''
        pre_sha256 = ''
        post_sha256 = ''
        archive_entry = $row.relative_path.Replace('\', '/')
        archive_status = 'PENDING_ACTIVE_SNAPSHOT'
        restore_status = 'PENDING'
        omission_reason = ''
    }
}
$runtimeRows | Export-Csv -LiteralPath (Join-Path $audit 'RUNTIME_PRESERVATION_MANIFEST.csv') -NoTypeInformation -Encoding utf8

# 30M derivation comparison is freshly generated using current 1M hashes.
$oneByRelative = @{}
$oneByHash = @{}
foreach ($row in $hashRows) {
    $oneByRelative[$row.relative_path] = $row
    if ($row.sha256) {
        if (-not $oneByHash.ContainsKey($row.sha256)) { $oneByHash[$row.sha256] = [Collections.Generic.List[string]]::new() }
        $oneByHash[$row.sha256].Add($row.relative_path)
    }
}
$thirtySnap = Get-FileSnapshot $thirtyM
$derivationRows = foreach ($row in $thirtySnap.Rows) {
    $hash30 = Get-Sha256 $row.full_path
    $sameRelative = if ($oneByRelative.ContainsKey($row.relative_path)) { $oneByRelative[$row.relative_path] } else { $null }
    $sameHashPaths = if ($oneByHash.ContainsKey($hash30)) { [string]::Join('|', @($oneByHash[$hash30])) } else { '' }
    $relation = if ($null -ne $sameRelative -and $sameRelative.sha256 -eq $hash30) { 'IDENTICAL_RELATIVE_PATH' } elseif ($null -ne $sameRelative) { 'DIFFERENT_RELATIVE_PATH' } elseif ($sameHashPaths) { 'IDENTICAL_OTHER_PATH' } else { 'THIRTY_M_ONLY' }
    [pscustomobject]@{
        relation = $relation
        relative_path_30m = $row.relative_path
        sha256_30m = $hash30
        size_bytes_30m = $row.size_bytes
        last_write_utc_30m = $row.last_write_utc
        relative_path_1m = if ($null -ne $sameRelative) { $sameRelative.relative_path } else { '' }
        sha256_1m = if ($null -ne $sameRelative) { $sameRelative.sha256 } else { '' }
        size_bytes_1m = if ($null -ne $sameRelative) { $sameRelative.size_bytes } else { '' }
        one_m_same_hash_paths = $sameHashPaths
    }
}
$derivationRows | Export-Csv -LiteralPath (Join-Path $audit 'DERIVATION_FILE_MAP.csv') -NoTypeInformation -Encoding utf8

# Process, health, environment and resource evidence.
$processRows = @(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -in @(20356, 13760) -or $_.CommandLine -match 'Delta_Engine_Pro4web|observe_execution_costs|uvicorn' } |
    Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine,CreationDate)
$processRows | Export-Csv -LiteralPath (Join-Path $audit 'RUN1_PROCESS_SNAPSHOT.csv') -NoTypeInformation -Encoding utf8
$healthStatus = 'UNAVAILABLE'
$healthError = ''
try {
    $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/api/health' -TimeoutSec 10
    $health | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath (Join-Path $audit 'RUN1_HEALTH.json') -Encoding utf8
    if ($null -ne $health.state) {
        $healthStatus = [string]$health.state
    } elseif ($null -ne $health.status) {
        $healthStatus = [string]$health.status
    }
} catch {
    $healthError = $_.Exception.Message
    @{ status = 'UNAVAILABLE'; error = $healthError } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $audit 'RUN1_HEALTH.json') -Encoding utf8
}
$pythonVersion = @(& python --version 2>&1) -join ' '
$pythonPath = @(& python -c 'import sys; print(sys.executable)' 2>&1) -join ' '
$pipFreezeHash = ''
try {
    $freeze = @(& python -m pip freeze --disable-pip-version-check 2>$null | Sort-Object)
    [IO.File]::WriteAllLines((Join-Path $audit 'RUN1_PIP_FREEZE.txt'), $freeze, [Text.UTF8Encoding]::new($false))
    $pipFreezeHash = Get-Sha256 (Join-Path $audit 'RUN1_PIP_FREEZE.txt')
} catch { [IO.File]::WriteAllText((Join-Path $audit 'RUN1_PIP_FREEZE.txt'), "UNAVAILABLE: $($_.Exception.Message)", [Text.UTF8Encoding]::new($false)) }
$requirementHash = Get-Sha256 (Join-Path $oneM 'requirements.txt')

$resourceRows = @(
    [pscustomobject]@{ resource = '1M_PRODUCT_ROOT'; canonical_path = $oneM; type = 'SOURCE_RUNTIME_ROOT'; owner = '1M'; phase0_action = 'READ_AND_PRESERVE'; status = 'EXISTS' }
    [pscustomobject]@{ resource = '30M_PRODUCT_ROOT'; canonical_path = $thirtyM; type = 'DERIVED_PRODUCT_ROOT'; owner = '30M'; phase0_action = 'READ_ONLY_DERIVATION_MAP'; status = 'EXISTS' }
    [pscustomobject]@{ resource = 'PHASE0_AUDIT_ROOT'; canonical_path = $audit; type = 'AUDIT'; owner = 'SEPARATION'; phase0_action = 'WRITE'; status = 'EXISTS' }
    [pscustomobject]@{ resource = 'EXTERNAL_PRESERVATION_ROOT'; canonical_path = $external; type = 'EXTERNAL_REMOTE_STORAGE'; owner = 'PRESERVATION'; phase0_action = 'WRITE_NEW_ONLY'; status = if (Test-Path -LiteralPath $external) { 'EXISTS' } else { 'MISSING' } }
    [pscustomobject]@{ resource = '1M_HTTP'; canonical_path = 'http://127.0.0.1:8080'; type = 'PROCESS_ENDPOINT'; owner = '1M'; phase0_action = 'READ_HEALTH_ONLY'; status = $healthStatus }
    [pscustomobject]@{ resource = '1M_DUCKDB'; canonical_path = $duckPath; type = 'DATABASE'; owner = '1M'; phase0_action = 'READ_HASH_ONLY_SOURCE'; status = if (Test-Path -LiteralPath $duckPath) { 'STABLE_IN_SAMPLE' } else { 'MISSING' } }
)
$resourceRows | Export-Csv -LiteralPath (Join-Path $audit 'ISOLATION_RESOURCE_MATRIX.csv') -NoTypeInformation -Encoding utf8

$classSummary = @($hashRows | Group-Object classification | Sort-Object Name | ForEach-Object { [pscustomobject]@{ classification = $_.Name; file_count = $_.Count; bytes = [int64](($_.Group | Measure-Object size_bytes -Sum).Sum) } })
$runtimeSummary = @($hashRows | Where-Object classification -eq 'C' | Group-Object runtime_state | Sort-Object Name | ForEach-Object { [pscustomobject]@{ runtime_state = $_.Name; file_count = $_.Count; bytes = [int64](($_.Group | Measure-Object size_bytes -Sum).Sum) } })
$modifiedCount = @($innerStatus | Where-Object { $_ -notlike '??*' }).Count
$untrackedCount = @($innerStatus | Where-Object { $_ -like '??*' }).Count
$summary = [ordered]@{
    audit_id = $auditId
    captured_utc = $capturedUtc
    outer_head = $outerHead
    outer_branch = $outerBranch
    gitlink_entry = $gitlink
    inner_head = $innerHead
    inner_branch = $innerBranch
    inner_modified_count = $modifiedCount
    inner_untracked_count = $untrackedCount
    tags = @($tags)
    remotes = @($remotes)
    one_m_file_count = $hashRows.Count
    one_m_total_bytes = [int64](($hashRows | Measure-Object size_bytes -Sum).Sum)
    class_summary = $classSummary
    runtime_summary = $runtimeSummary
    activity_changes = @($activity)
    enumeration_errors_start = @($snap1.Errors)
    enumeration_errors_end = @($snap2.Errors)
    reparse_link_count = $linkRows.Count
    hardlink_multiple_count = @($hardlinkRows | Where-Object { ([int]($_.link_count -as [int])) -gt 1 }).Count
    duckdb_hash_before = $duckHashBefore
    duckdb_hash_after = $duckHashAfter
    duckdb_hash_stable = ($duckHashBefore -eq $duckHashAfter)
    parquet_before = $pq1
    parquet_after = $pq2
    health_status = $healthStatus
    health_error = $healthError
    python_version = $pythonVersion
    python_executable = $pythonPath
    requirements_sha256 = $requirementHash
    pip_freeze_sha256 = $pipFreezeHash
    thirty_m_file_count = @($derivationRows).Count
    gate_0a_r_required = ($gateReasons.Count -gt 0)
    gate_0a_r_reasons = @($gateReasons)
}
$summary | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath (Join-Path $audit 'RUN1_REMEASUREMENT.json') -Encoding utf8

Write-Output ("RUN1_FRESH_PREFLIGHT_COMPLETE gate_0a_r_required={0} files={1} runtime={2} active={3}" -f ($gateReasons.Count -gt 0), $hashRows.Count, @($runtimeRows).Count, $activeSet.Count)
