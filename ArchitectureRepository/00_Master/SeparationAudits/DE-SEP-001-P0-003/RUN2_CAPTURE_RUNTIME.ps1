param(
    [string]$ExternalRoot = 'I:\マイドライブ\DeltaEngine_Preservation\DE-SEP-001-P0-003',
    [string]$VerifyRoot = '',
    [switch]$KeepVerify,
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$auditId = 'DE-SEP-001-P0-003'
$audit = $PSScriptRoot
$repoRoot = (Resolve-Path (Join-Path $audit '..\..\..\..')).Path
$oneM = (Resolve-Path (Join-Path $repoRoot 'Delta_Engine_Pro4web')).Path
$manifestPath = Join-Path $audit 'RUNTIME_PRESERVATION_MANIFEST.csv'
$restoreCsvPath = Join-Path $audit 'RUN2_RUNTIME_RESTORE_VERIFICATION.csv'
$activeCsvPath = Join-Path $audit 'RUN2_ACTIVE_SNAPSHOT_FINAL.csv'
$resultPath = Join-Path $audit 'RUN2_RUNTIME_ARCHIVE_RESULT.json'
$progressPath = Join-Path $audit 'RUN2_RUNTIME_CAPTURE_PROGRESS.json'
$duckResultPath = Join-Path $audit 'RUN2_DUCKDB_RESTORE_VERIFICATION.json'
$duckVerifyScript = Join-Path $audit 'RUN2_VERIFY_RESTORED_DUCKDB.py'
$finalArchive = Join-Path $ExternalRoot 'ONE_M_RUNTIME_FORENSIC.zip'
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$partialDirectory = Join-Path $ExternalRoot 'C_STAGE'
$partialArchive = Join-Path $partialDirectory ("ONE_M_RUNTIME_FORENSIC.$stamp.partial.zip")
$captureStarted = (Get-Date).ToUniversalTime()
$verifyCreated = $false
$zip = $null
$archiveStream = $null

function Write-JsonAtomic([string]$Path, [object]$Value) {
    $temporary = "$Path.tmp"
    $json = $Value | ConvertTo-Json -Depth 30
    [IO.File]::WriteAllText($temporary, $json, [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Write-Progress([string]$Phase, [int64]$Completed, [int64]$Total, [string]$Detail) {
    Write-JsonAtomic $progressPath ([ordered]@{
        audit_id = $auditId
        updated_utc = (Get-Date).ToUniversalTime().ToString('o')
        phase = $Phase
        completed = $Completed
        total = $Total
        detail = $Detail
        partial_archive = $partialArchive
        final_archive = $finalArchive
    })
    Write-Output ("PROGRESS phase={0} completed={1}/{2} detail={3}" -f $Phase, $Completed, $Total, $Detail)
}

function Open-SharedRead([string]$Path) {
    return [IO.File]::Open(
        $Path,
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        [IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete
    )
}

function Finalize-Sha([Security.Cryptography.HashAlgorithm]$Sha) {
    [void]$Sha.TransformFinalBlock([byte[]]::new(0), 0, 0)
    return [Convert]::ToHexString($Sha.Hash)
}

function Get-StreamHash([IO.Stream]$Stream, [Nullable[int64]]$Limit) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $buffer = New-Object byte[] 1048576
        $copied = [int64]0
        $hasLimit = $null -ne $Limit
        $limitBytes = if ($hasLimit) { [int64]$Limit } else { [int64]0 }
        while ($true) {
            if ($hasLimit -and $copied -ge $limitBytes) { break }
            $take = $buffer.Length
            if ($hasLimit) { $take = [int][Math]::Min([int64]$take, $limitBytes - $copied) }
            $read = $Stream.Read($buffer, 0, $take)
            if ($read -le 0) {
                if ($hasLimit -and $copied -ne $limitBytes) {
                    throw "Unexpected EOF: expected $limitBytes, copied $copied"
                }
                break
            }
            [void]$sha.TransformBlock($buffer, 0, $read, $null, 0)
            $copied += $read
        }
        $hash = Finalize-Sha $sha
        return [pscustomobject]@{ bytes = $copied; sha256 = $hash }
    } finally {
        $sha.Dispose()
    }
}

function Get-FileHashShared([string]$Path, [Nullable[int64]]$Limit = $null) {
    $stream = Open-SharedRead $Path
    try { return Get-StreamHash $stream $Limit }
    finally { $stream.Dispose() }
}

function Add-FileEntry(
    [IO.Compression.ZipArchive]$Archive,
    [string]$SourcePath,
    [string]$EntryName,
    [int64]$ExpectedBytes
) {
    $source = Open-SharedRead $SourcePath
    try {
        if ($source.Length -lt $ExpectedBytes) {
            throw "Source shorter than expected for ${SourcePath}: $($source.Length) < $ExpectedBytes"
        }
        $entry = $Archive.CreateEntry($EntryName, [IO.Compression.CompressionLevel]::Fastest)
        try { $entry.LastWriteTime = (Get-Item -LiteralPath $SourcePath).LastWriteTime }
        catch { }
        $destination = $entry.Open()
        $sha = [Security.Cryptography.SHA256]::Create()
        try {
            $buffer = New-Object byte[] 1048576
            $copied = [int64]0
            while ($copied -lt $ExpectedBytes) {
                $take = [int][Math]::Min([int64]$buffer.Length, $ExpectedBytes - $copied)
                $read = $source.Read($buffer, 0, $take)
                if ($read -le 0) { throw "Unexpected EOF while archiving $SourcePath" }
                $destination.Write($buffer, 0, $read)
                [void]$sha.TransformBlock($buffer, 0, $read, $null, 0)
                $copied += $read
            }
            $hash = Finalize-Sha $sha
            return [pscustomobject]@{ bytes = $copied; sha256 = $hash }
        } finally {
            $sha.Dispose()
            $destination.Dispose()
        }
    } finally {
        $source.Dispose()
    }
}

function Add-BytesEntry(
    [IO.Compression.ZipArchive]$Archive,
    [byte[]]$Bytes,
    [string]$EntryName
) {
    $entry = $Archive.CreateEntry($EntryName, [IO.Compression.CompressionLevel]::Fastest)
    $destination = $entry.Open()
    try { $destination.Write($Bytes, 0, $Bytes.Length) }
    finally { $destination.Dispose() }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = [Convert]::ToHexString($sha.ComputeHash($Bytes)) }
    finally { $sha.Dispose() }
    return [pscustomobject]@{ bytes = [int64]$Bytes.Length; sha256 = $hash }
}

function Get-NewlineCutoff([string]$Path) {
    $stream = Open-SharedRead $Path
    try {
        $length = [int64]$stream.Length
        if ($length -eq 0) {
            return [pscustomobject]@{ cutoff = [int64]0; method = 'SHARED_READ_ZERO_LENGTH' }
        }
        $tailLength = [int][Math]::Min([int64]1048576, $length)
        $tail = New-Object byte[] $tailLength
        [void]$stream.Seek($length - $tailLength, [IO.SeekOrigin]::Begin)
        $read = $stream.Read($tail, 0, $tailLength)
        $lastLf = -1
        for ($index = $read - 1; $index -ge 0; $index--) {
            if ($tail[$index] -eq 10) { $lastLf = $index; break }
        }
        if ($lastLf -lt 0) { throw "No complete newline boundary found: $Path" }
        return [pscustomobject]@{
            cutoff = [int64](($length - $tailLength) + $lastLf + 1)
            method = 'SHARED_READ_FIXED_NEWLINE_PREFIX'
        }
    } finally {
        $stream.Dispose()
    }
}

function Read-AtomicJson([string]$Path) {
    $lastError = $null
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        try {
            $stream = Open-SharedRead $Path
            try {
                $memory = [IO.MemoryStream]::new()
                try { $stream.CopyTo($memory); $bytes = $memory.ToArray() }
                finally { $memory.Dispose() }
            } finally { $stream.Dispose() }
            $text = [Text.Encoding]::UTF8.GetString($bytes)
            $parsed = $text | ConvertFrom-Json -ErrorAction Stop
            return [pscustomobject]@{ bytes = $bytes; parsed = $parsed; attempts = $attempt }
        } catch {
            $lastError = $_.Exception.Message
            Start-Sleep -Milliseconds 100
        }
    }
    throw "Atomic JSON snapshot failed after retries: $lastError"
}

function Assert-SafeEntry([string]$EntryName) {
    if ([string]::IsNullOrWhiteSpace($EntryName)) { throw 'Empty archive entry' }
    if ($EntryName.Contains('\')) { throw "Backslash in archive entry: $EntryName" }
    if ($EntryName.StartsWith('/') -or [IO.Path]::IsPathRooted($EntryName)) {
        throw "Rooted archive entry: $EntryName"
    }
    if ($EntryName -match '(^|/)\.\.(/|$)') { throw "Traversal archive entry: $EntryName" }
}

function Ensure-ManifestColumn([object[]]$Rows, [string]$Name) {
    foreach ($row in $Rows) {
        if ($null -eq $row.PSObject.Properties[$Name]) {
            $row | Add-Member -NotePropertyName $Name -NotePropertyValue ''
        }
    }
}

try {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Missing runtime manifest: $manifestPath" }
    if (-not (Test-Path -LiteralPath $duckVerifyScript -PathType Leaf)) { throw "Missing DuckDB verifier: $duckVerifyScript" }
    if (-not (Test-Path -LiteralPath $ExternalRoot -PathType Container)) { throw "Missing external root: $ExternalRoot" }
    if (Test-Path -LiteralPath $finalArchive) { throw "Final runtime archive already exists; overwrite refused: $finalArchive" }
    if (-not (Test-Path -LiteralPath $partialDirectory -PathType Container)) { throw "Missing C_STAGE: $partialDirectory" }
    if (Test-Path -LiteralPath $partialArchive) { throw "Partial path collision: $partialArchive" }

    $externalItem = Get-Item -LiteralPath $ExternalRoot
    if (($externalItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "External root is a reparse point: $ExternalRoot"
    }

    $rows = @(Import-Csv -LiteralPath $manifestPath)
    if ($rows.Count -ne 56945) { throw "Unexpected runtime manifest count: $($rows.Count)" }
    Ensure-ManifestColumn $rows 'capture_started_utc'
    Ensure-ManifestColumn $rows 'capture_completed_utc'
    Ensure-ManifestColumn $rows 'period_metadata'
    $stableRows = @($rows | Where-Object runtime_state -eq 'STABLE_DATA')
    $activeRows = @($rows | Where-Object runtime_state -eq 'ACTIVE_RUNTIME')
    if ($stableRows.Count -ne 56938 -or $activeRows.Count -ne 7) {
        throw "Unexpected stable/active counts: $($stableRows.Count)/$($activeRows.Count)"
    }

    $entrySet = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($row in $rows) {
        Assert-SafeEntry $row.archive_entry
        if (-not $entrySet.Add($row.archive_entry)) { throw "Duplicate archive entry: $($row.archive_entry)" }
        $sourcePath = Join-Path $oneM $row.relative_path
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { throw "Missing source file: $sourcePath" }
        $item = Get-Item -LiteralPath $sourcePath
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Reparse source refused: $sourcePath"
        }
        if ($row.runtime_state -eq 'STABLE_DATA' -and [int64]$item.Length -ne [int64]$row.source_size_at_inventory) {
            throw "Stable source size differs before archive: $($row.relative_path) inventory=$($row.source_size_at_inventory) current=$($item.Length)"
        }
    }

    if ([string]::IsNullOrWhiteSpace($VerifyRoot)) {
        $VerifyRoot = Join-Path ([IO.Path]::GetTempPath()) ("DE-SEP-001-P0-003_VERIFY_C_$stamp")
    }
    $VerifyRoot = [IO.Path]::GetFullPath($VerifyRoot)
    $tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $VerifyRoot.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase)) {
        throw "VerifyRoot must remain inside the current temporary root: $VerifyRoot"
    }
    if ($VerifyRoot.StartsWith($oneM + '\', [StringComparison]::OrdinalIgnoreCase) -or
        $VerifyRoot.StartsWith((Resolve-Path (Join-Path $repoRoot 'Delta_Engine_30M')).Path + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "VerifyRoot must be outside both product roots: $VerifyRoot"
    }
    if (Test-Path -LiteralPath $VerifyRoot) { throw "VerifyRoot already exists: $VerifyRoot" }

    Write-Progress 'PRECHECK_COMPLETE' 0 $rows.Count 'manifest, entry safety, source existence, and no-overwrite checks passed'
    if ($PreflightOnly) {
        Write-Output ("RUN2_RUNTIME_PREFLIGHT_PASS rows={0} stable={1} active={2} partial={3}" -f $rows.Count, $stableRows.Count, $activeRows.Count, $partialArchive)
        return
    }

    $archiveStream = [IO.File]::Open(
        $partialArchive,
        [IO.FileMode]::CreateNew,
        [IO.FileAccess]::ReadWrite,
        [IO.FileShare]::Read
    )
    $zip = [IO.Compression.ZipArchive]::new($archiveStream, [IO.Compression.ZipArchiveMode]::Create, $false)
    $processed = 0
    foreach ($row in $stableRows) {
        $sourcePath = Join-Path $oneM $row.relative_path
        $expectedBytes = [int64]$row.source_size_at_inventory
        $capture = Add-FileEntry $zip $sourcePath $row.archive_entry $expectedBytes
        if ($capture.bytes -ne $expectedBytes -or $capture.sha256 -ne $row.source_sha256_at_inventory) {
            throw "Stable capture mismatch: $($row.relative_path)"
        }
        $row.snapshot_size_bytes = [string]$capture.bytes
        $row.snapshot_sha256 = $capture.sha256
        $row.pre_sha256 = $row.source_sha256_at_inventory
        $row.capture_started_utc = $captureStarted.ToString('o')
        $row.archive_status = 'INCLUDED_STABLE'
        if ($row.relative_path -eq 'data\duckdb\orderflow.duckdb') {
            $row.period_metadata = 'SEE_RUN2_DUCKDB_RESTORE_VERIFICATION.json'
        }
        $processed++
        if (($processed % 2000) -eq 0) {
            Write-Progress 'ZIP_STABLE' $processed $rows.Count $row.relative_path
        }
    }

    $activeEvidence = [Collections.Generic.List[object]]::new()
    foreach ($row in $activeRows) {
        $sourcePath = Join-Path $oneM $row.relative_path
        $snapshotStarted = (Get-Date).ToUniversalTime()
        if ($row.capture_method -eq 'ATOMIC_JSON_SNAPSHOT') {
            $atomic = Read-AtomicJson $sourcePath
            $capture = Add-BytesEntry $zip $atomic.bytes $row.archive_entry
            $updatedAt = ''
            if ($null -ne $atomic.parsed.PSObject.Properties['updated_at']) { $updatedAt = [string]$atomic.parsed.updated_at }
            $row.snapshot_size_bytes = [string]$capture.bytes
            $row.snapshot_sha256 = $capture.sha256
            $row.pre_sha256 = $capture.sha256
            $row.post_sha256 = $capture.sha256
            $row.archive_status = 'SNAPSHOT_CONSISTENT'
            $row.capture_method = 'ATOMIC_JSON_SNAPSHOT'
            $row.period_metadata = if ($updatedAt) { "updated_at=$updatedAt" } else { 'VALID_JSON_NO_UPDATED_AT' }
            $activeEvidence.Add([pscustomobject]@{
                relative_path = $row.relative_path
                method = $row.capture_method
                cutoff_bytes = $capture.bytes
                snapshot_sha256 = $capture.sha256
                prefix_hash_before = $capture.sha256
                prefix_hash_after = $capture.sha256
                captured_utc = $snapshotStarted.ToString('o')
                json_updated_at = $updatedAt
                validation = 'JSON_PARSE_PASS'
            })
        } else {
            $boundary = Get-NewlineCutoff $sourcePath
            $before = Get-FileHashShared $sourcePath ([Nullable[int64]]$boundary.cutoff)
            $capture = Add-FileEntry $zip $sourcePath $row.archive_entry $boundary.cutoff
            $after = Get-FileHashShared $sourcePath ([Nullable[int64]]$boundary.cutoff)
            if ($before.sha256 -ne $capture.sha256 -or $capture.sha256 -ne $after.sha256) {
                throw "Active prefix changed during capture: $($row.relative_path)"
            }
            $row.snapshot_size_bytes = [string]$capture.bytes
            $row.snapshot_sha256 = $capture.sha256
            $row.pre_sha256 = $before.sha256
            $row.post_sha256 = $after.sha256
            $row.archive_status = 'SNAPSHOT_CONSISTENT'
            $row.capture_method = $boundary.method
            $row.period_metadata = "complete_newline_cutoff_bytes=$($boundary.cutoff)"
            $activeEvidence.Add([pscustomobject]@{
                relative_path = $row.relative_path
                method = $boundary.method
                cutoff_bytes = $boundary.cutoff
                snapshot_sha256 = $capture.sha256
                prefix_hash_before = $before.sha256
                prefix_hash_after = $after.sha256
                captured_utc = $snapshotStarted.ToString('o')
                json_updated_at = ''
                validation = 'PREFIX_STABLE_PASS'
            })
        }
        $row.capture_started_utc = $snapshotStarted.ToString('o')
        $processed++
        Write-Progress 'ZIP_ACTIVE' $processed $rows.Count $row.relative_path
    }
    $zip.Dispose()
    $zip = $null
    $archiveStream.Dispose()
    $archiveStream = $null
    Write-Progress 'ZIP_CLOSED' $processed $rows.Count 'partial archive closed cleanly'

    $postChecked = 0
    foreach ($row in $stableRows) {
        $sourcePath = Join-Path $oneM $row.relative_path
        $item = Get-Item -LiteralPath $sourcePath
        if ([int64]$item.Length -ne [int64]$row.source_size_at_inventory) {
            throw "Stable source size changed after capture: $($row.relative_path)"
        }
        $post = Get-FileHashShared $sourcePath
        $row.post_sha256 = $post.sha256
        if ($post.sha256 -ne $row.pre_sha256 -or $post.sha256 -ne $row.snapshot_sha256) {
            throw "Stable source hash changed after capture: $($row.relative_path)"
        }
        $postChecked++
        if (($postChecked % 2000) -eq 0) {
            Write-Progress 'SOURCE_POST_HASH' $postChecked $stableRows.Count $row.relative_path
        }
    }
    Write-Progress 'SOURCE_POST_HASH' $stableRows.Count $stableRows.Count 'all stable source hashes match inventory and archive bytes'

    $readZip = [IO.Compression.ZipFile]::OpenRead($partialArchive)
    try {
        if ($readZip.Entries.Count -ne $rows.Count) {
            throw "Archive entry count mismatch: $($readZip.Entries.Count) != $($rows.Count)"
        }
        $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
        foreach ($entry in $readZip.Entries) {
            Assert-SafeEntry $entry.FullName
            if (-not $seen.Add($entry.FullName)) { throw "Duplicate archive entry after close: $($entry.FullName)" }
            if (-not $entrySet.Contains($entry.FullName)) { throw "Unexpected archive entry: $($entry.FullName)" }
        }
    } finally { $readZip.Dispose() }

    [IO.Compression.ZipFile]::ExtractToDirectory($partialArchive, $VerifyRoot, $false)
    $verifyCreated = $true
    Write-Progress 'RESTORE_EXTRACTED' 0 $rows.Count $VerifyRoot

    $restored = 0
    foreach ($row in $rows) {
        $restoredPath = Join-Path $VerifyRoot $row.relative_path
        if (-not (Test-Path -LiteralPath $restoredPath -PathType Leaf)) {
            throw "Restored file missing: $($row.relative_path)"
        }
        $item = Get-Item -LiteralPath $restoredPath
        $hash = Get-FileHashShared $restoredPath
        if ([int64]$item.Length -ne [int64]$row.snapshot_size_bytes -or $hash.sha256 -ne $row.snapshot_sha256) {
            throw "Restored file mismatch: $($row.relative_path)"
        }
        $row.restore_status = 'PASS'
        $row.capture_completed_utc = (Get-Date).ToUniversalTime().ToString('o')
        $restored++
        if (($restored % 2000) -eq 0) {
            Write-Progress 'RESTORE_HASH' $restored $rows.Count $row.relative_path
        }
    }

    $restoredFiles = @(Get-ChildItem -LiteralPath $VerifyRoot -Recurse -Force -File)
    if ($restoredFiles.Count -ne $rows.Count) {
        throw "Restored file count mismatch: $($restoredFiles.Count) != $($rows.Count)"
    }
    $restoredStatus = Join-Path $VerifyRoot 'data\execution_costs\status.json'
    if (Test-Path -LiteralPath $restoredStatus) {
        [void](Get-Content -Raw -LiteralPath $restoredStatus | ConvertFrom-Json -ErrorAction Stop)
    }
    Write-Progress 'RESTORE_HASH' $rows.Count $rows.Count 'all restored paths, sizes, and hashes match'

    $restoredDuckDb = Join-Path $VerifyRoot 'data\duckdb\orderflow.duckdb'
    $pythonExe = (Get-Command python -ErrorAction Stop).Source
    & $pythonExe $duckVerifyScript --db $restoredDuckDb --output $duckResultPath
    if ($LASTEXITCODE -ne 0) { throw "Restored DuckDB verification failed with exit code $LASTEXITCODE" }
    $duckResult = Get-Content -Raw -LiteralPath $duckResultPath | ConvertFrom-Json
    if ($duckResult.status -ne 'PASS') { throw "Restored DuckDB result is not PASS: $($duckResult.status)" }
    Write-Progress 'DUCKDB_RESTORE' 1 1 "tables=$($duckResult.table_count), periods=$($duckResult.period_table_count)"

    $partialHash = (Get-FileHash -LiteralPath $partialArchive -Algorithm SHA256).Hash.ToUpperInvariant()
    $partialSize = (Get-Item -LiteralPath $partialArchive).Length
    if (Test-Path -LiteralPath $finalArchive) { throw "Final archive appeared during capture; overwrite refused: $finalArchive" }
    [IO.File]::Move($partialArchive, $finalArchive)
    $finalHash = (Get-FileHash -LiteralPath $finalArchive -Algorithm SHA256).Hash.ToUpperInvariant()
    $finalSize = (Get-Item -LiteralPath $finalArchive).Length
    if ($finalHash -ne $partialHash -or $finalSize -ne $partialSize) {
        throw 'Final archive re-read differs after external rename'
    }

    $rows | Export-Csv -LiteralPath $manifestPath -NoTypeInformation -Encoding utf8
    $rows | Select-Object relative_path,runtime_state,snapshot_size_bytes,snapshot_sha256,pre_sha256,post_sha256,archive_entry,archive_status,restore_status,capture_method,capture_started_utc,capture_completed_utc,period_metadata |
        Export-Csv -LiteralPath $restoreCsvPath -NoTypeInformation -Encoding utf8
    $activeEvidence | Export-Csv -LiteralPath $activeCsvPath -NoTypeInformation -Encoding utf8

    $cleanupPerformed = $false
    if (-not $KeepVerify) {
        $verifyFull = [IO.Path]::GetFullPath($VerifyRoot)
        if (-not $verifyFull.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Unsafe verify cleanup target: $verifyFull"
        }
        Remove-Item -LiteralPath $verifyFull -Recurse -Force
        $cleanupPerformed = -not (Test-Path -LiteralPath $verifyFull)
    }

    $captureCompleted = (Get-Date).ToUniversalTime()
    $result = [ordered]@{
        audit_id = $auditId
        status = 'PASS'
        capture_started_utc = $captureStarted.ToString('o')
        capture_completed_utc = $captureCompleted.ToString('o')
        final_archive = $finalArchive
        final_archive_size_bytes = $finalSize
        final_archive_sha256 = $finalHash
        external_reread_hash_match = $true
        entry_count = $rows.Count
        stable_count = $stableRows.Count
        active_count = $activeRows.Count
        pending_active_snapshot_count = @($rows | Where-Object archive_status -eq 'PENDING_ACTIVE_SNAPSHOT').Count
        restore_pass_count = @($rows | Where-Object restore_status -eq 'PASS').Count
        source_post_hash_match_count = @($stableRows | Where-Object { $_.pre_sha256 -eq $_.post_sha256 -and $_.post_sha256 -eq $_.snapshot_sha256 }).Count
        duckdb_restore_status = $duckResult.status
        duckdb_table_count = $duckResult.table_count
        duckdb_period_table_count = $duckResult.period_table_count
        verify_root = $VerifyRoot
        verify_root_removed = $cleanupPerformed
        source_product_modified = $false
        source_product_process_stopped_or_restarted = $false
    }
    Write-JsonAtomic $resultPath $result
    Write-Progress 'COMPLETE' $rows.Count $rows.Count "archive_sha256=$finalHash"
    Write-Output ("RUN2_RUNTIME_ARCHIVE_PASS path={0} bytes={1} sha256={2}" -f $finalArchive, $finalSize, $finalHash)
} catch {
    if ($null -ne $zip) { try { $zip.Dispose() } catch { } }
    if ($null -ne $archiveStream) { try { $archiveStream.Dispose() } catch { } }
    $failure = [ordered]@{
        audit_id = $auditId
        status = 'FAIL'
        failed_utc = (Get-Date).ToUniversalTime().ToString('o')
        error_type = $_.Exception.GetType().FullName
        error = $_.Exception.Message
        partial_archive = $partialArchive
        partial_exists = (Test-Path -LiteralPath $partialArchive)
        final_archive = $finalArchive
        final_exists = (Test-Path -LiteralPath $finalArchive)
        verify_root = $VerifyRoot
        verify_root_exists = if ([string]::IsNullOrWhiteSpace($VerifyRoot)) { $false } else { Test-Path -LiteralPath $VerifyRoot }
        source_product_modified = $false
        source_product_process_stopped_or_restarted = $false
    }
    Write-JsonAtomic $resultPath $failure
    Write-Progress 'FAILED' 0 0 $_.Exception.Message
    throw
}