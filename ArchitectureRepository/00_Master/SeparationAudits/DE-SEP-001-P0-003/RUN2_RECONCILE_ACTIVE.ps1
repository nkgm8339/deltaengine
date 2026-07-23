param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$audit = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $audit '..\..\..\..')).Path
$oneM = (Resolve-Path (Join-Path $repoRoot 'Delta_Engine_Pro4web')).Path
$filesetPath = Join-Path $audit 'PRESERVATION_FILESET_SHA256.csv'
$runtimePath = Join-Path $audit 'RUNTIME_PRESERVATION_MANIFEST.csv'
$evidencePath = Join-Path $audit 'RUN2_LIVE_SAFE_EVIDENCE.csv'
$fileset = @(Import-Csv -LiteralPath $filesetPath)
$runtime = @(Import-Csv -LiteralPath $runtimePath)
$evidence = @(Import-Csv -LiteralPath $evidencePath)

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

function Test-SharedSnapshot([string]$path) {
    $stream = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete)
    try {
        $length = $stream.Length
        if ($length -eq 0) { $cutoff = 0; $method = 'SHARED_READ_ZERO_LENGTH' }
        else {
            $tailLength = [int][Math]::Min([int64]1048576, $length)
            $tail = New-Object byte[] $tailLength
            $stream.Seek($length - $tailLength, [IO.SeekOrigin]::Begin) | Out-Null
            $read = $stream.Read($tail, 0, $tailLength)
            $lastLf = -1
            for ($i = $read - 1; $i -ge 0; $i--) { if ($tail[$i] -eq 10) { $lastLf = $i; break } }
            if ($lastLf -lt 0) { throw "No complete newline boundary found: $path" }
            $cutoff = ($length - $tailLength) + $lastLf + 1
            $method = 'SHARED_READ_FIXED_NEWLINE_PREFIX'
        }
    } finally { $stream.Dispose() }
    $hash1 = Get-PrefixHash $path $cutoff
    Start-Sleep -Seconds 2
    $hash2 = Get-PrefixHash $path $cutoff
    return [pscustomobject]@{ method = $method; cutoff = $cutoff; hash1 = $hash1; hash2 = $hash2; pass = ($hash1 -eq $hash2) }
}

$lockedRows = @($fileset | Where-Object hash_status -like 'ERROR:*')
$newEvidence = [Collections.Generic.List[object]]::new()
foreach ($row in $lockedRows) {
    if ($row.relative_path -notlike '*.log' -and $row.relative_path -notlike '*.csv') { throw "Locked file has no approved live-safe method: $($row.relative_path)" }
    $probe = Test-SharedSnapshot (Join-Path $oneM $row.relative_path)
    $newEvidence.Add([pscustomobject]@{
        relative_path = $row.relative_path
        method = $probe.method
        cutoff_bytes = $probe.cutoff
        hash_before = $probe.hash1
        hash_after = $probe.hash2
        pass = $probe.pass
        detail = 'LOCKED_BY_LIVE_PROCESS; CAPTURE_AS_ACTIVE_RUNTIME'
    })
    if (-not $probe.pass) { throw "Live-safe prefix changed: $($row.relative_path)" }
}

$evidenceMap = @{}
foreach ($row in $evidence) { $evidenceMap[$row.relative_path] = $row }
foreach ($row in $newEvidence) { $evidenceMap[$row.relative_path] = $row }
@($evidenceMap.Values | Sort-Object relative_path) | Export-Csv -LiteralPath $evidencePath -NoTypeInformation -Encoding utf8

$activePaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($row in @($evidenceMap.Values)) { [void]$activePaths.Add($row.relative_path) }
foreach ($row in $fileset) {
    if ($activePaths.Contains($row.relative_path)) {
        $row.runtime_state = 'ACTIVE_RUNTIME'
        $row.hash_status = 'ACTIVE_RUNTIME_INITIAL_OBSERVATION_ONLY; FINAL_SNAPSHOT_IN_RUNTIME_MANIFEST'
    }
}
$fileset | Export-Csv -LiteralPath $filesetPath -NoTypeInformation -Encoding utf8

foreach ($row in $runtime) {
    if ($activePaths.Contains($row.relative_path)) {
        $row.runtime_state = 'ACTIVE_RUNTIME'
        $matchingEvidence = $evidenceMap[$row.relative_path]
        $row.capture_method = if ($row.relative_path -eq 'data\execution_costs\status.json') { 'ATOMIC_JSON_SNAPSHOT' } else { $matchingEvidence.method }
        $row.archive_status = 'PENDING_ACTIVE_SNAPSHOT'
    } else {
        $row.runtime_state = 'STABLE_DATA'
        $row.capture_method = 'PRE_POST_HASH_AND_PHYSICAL_ZIP'
        $row.archive_status = 'PENDING_STABLE_CAPTURE'
    }
}
$runtime | Export-Csv -LiteralPath $runtimePath -NoTypeInformation -Encoding utf8
Write-Output ("RUN2_ACTIVE_RECONCILED locked={0} active={1}" -f $lockedRows.Count, $activePaths.Count)
