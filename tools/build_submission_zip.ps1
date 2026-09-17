param(
    [string]$Destination
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$workspaceRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $projectRoot)).Path
if (-not $Destination) {
    $Destination = Join-Path $workspaceRoot "Head_Gesture_Epuck_Submission_20260808_FINAL.zip"
}
$destinationPath = [IO.Path]::GetFullPath($Destination)
$workspacePrefix = $workspaceRoot.TrimEnd('\') + '\'
if (-not $destinationPath.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase) -or
    [IO.Path]::GetExtension($destinationPath) -ne ".zip") {
    throw "Destination must be a ZIP directly within the approved workspace tree: $workspaceRoot"
}

$buildId = [Guid]::NewGuid().ToString("N")
$stage = Join-Path $workspaceRoot "_submission_stage_$buildId"
$qa = Join-Path $workspaceRoot "_submission_qa_$buildId"
$temporaryZip = Join-Path $workspaceRoot "_submission_archive_$buildId.zip"

function Assert-TemporaryPath([string]$path, [string]$requiredPrefix) {
    $full = [IO.Path]::GetFullPath($path)
    $leaf = Split-Path -Leaf $full
    if (-not $full.StartsWith($workspacePrefix, [StringComparison]::OrdinalIgnoreCase) -or
        -not $leaf.StartsWith($requiredPrefix, [StringComparison]::Ordinal)) {
        throw "Unsafe temporary path: $full"
    }
}

function Get-RelativePathCompat([string]$basePath, [string]$targetPath) {
    $baseFull = [IO.Path]::GetFullPath($basePath).TrimEnd('\') + '\'
    $targetFull = [IO.Path]::GetFullPath($targetPath)
    if (-not $targetFull.StartsWith($baseFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target path is outside its expected base: $targetFull"
    }
    return $targetFull.Substring($baseFull.Length)
}

Assert-TemporaryPath $stage "_submission_stage_"
Assert-TemporaryPath $qa "_submission_qa_"
Assert-TemporaryPath $temporaryZip "_submission_archive_"

function Copy-PackageFile([string]$source, [string]$relativeDestination) {
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required package file is missing: $source"
    }
    $target = Join-Path $stage $relativeDestination
    $parent = Split-Path -Parent $target
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
}

function Copy-PackageTree([string]$sourceRoot, [string]$relativeDestination) {
    if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) {
        throw "Required package directory is missing: $sourceRoot"
    }
    foreach ($file in Get-ChildItem -LiteralPath $sourceRoot -Recurse -File) {
        if ($file.Name -like "*.pyc" -or $file.FullName -match '[\\/]__pycache__[\\/]') {
            continue
        }
        $relative = Get-RelativePathCompat $sourceRoot $file.FullName
        Copy-PackageFile $file.FullName (Join-Path $relativeDestination $relative)
    }
}

function Copy-EvidenceRun([string]$runName, [string]$destinationName) {
    $source = Join-Path $projectRoot "validation_runs\$runName"
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        throw "Required evidence run is missing: $source"
    }
    foreach ($file in Get-ChildItem -LiteralPath $source -Recurse -File) {
        if ($file.Name -like "*raw.mp4") {
            continue
        }
        $relative = Get-RelativePathCompat $source $file.FullName
        Copy-PackageFile $file.FullName (Join-Path "evidence\runs\$destinationName" $relative)
    }
}

function Get-StreamSha256([IO.Stream]$stream) {
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
    }
}

New-Item -ItemType Directory -Path $stage | Out-Null

try {
    foreach ($file in @(
        "AGENTS.md",
        "CLIENT_READINESS_AUDIT.md",
        "VOICE_OVERRIDE_FIX.md",
        "CODE_EXPLANATION.md",
        "compose.webots.yaml",
        "instructions.md",
        "PACKAGE_CONTENTS.md",
        "plan.md",
        "PROJECT_CHANGES_CHECKLIST.md",
        "README.md",
        "requirements.txt",
        "SUBMISSION_GUIDE.md"
    )) {
        Copy-PackageFile (Join-Path $projectRoot $file) $file
    }

    Copy-PackageTree (Join-Path $projectRoot "controllers\epuck_waypoint_controller") "controllers\epuck_waypoint_controller"
    Copy-PackageTree (Join-Path $projectRoot "models\vosk-model-small-en-us-0.15") "models\vosk-model-small-en-us-0.15"
    Copy-PackageTree (Join-Path $projectRoot "tests") "tests"
    Copy-PackageTree (Join-Path $projectRoot "tools") "tools"
    Copy-PackageTree (Join-Path $projectRoot "protos") "protos"

    Copy-PackageFile (Join-Path $projectRoot "validation_runs\client_clean_setup.log") "evidence\client_audit\clean_setup.log"
    Copy-PackageFile (Join-Path $projectRoot "validation_runs\client_audit_docker_final.log") "evidence\client_audit\docker_all.log"
    Copy-PackageFile (Join-Path $projectRoot "validation_runs\voice_override_final_20260911.log") "evidence\voice_override\all.log"
    Copy-PackageFile (Join-Path $projectRoot "validation_runs\voice_override_midroute_20260911.log") "evidence\voice_override\midroute.log"

    # The main e-puck world is the only WBT required by the submitted project.
    Copy-PackageFile (Join-Path $projectRoot "worlds\epuck_waypoint_navigation.wbt") "worlds\epuck_waypoint_navigation.wbt"

    foreach ($file in @(
        "README.md",
        "head_gesture_video_controlled_robot.mp4",
        "head_gesture_video_controlled_robot_contact_sheet.jpg",
        "head_gesture_video_controlled_robot_thumbnail.jpg",
        "head_gesture_video_controlled_robot_stop_frame.jpg"
    )) {
        Copy-PackageFile (Join-Path $projectRoot "demo\$file") "demo\$file"
    }

    Copy-PackageFile (Join-Path $workspaceRoot "35056702_Documentation.docx") "documents\35056702_Documentation.docx"
    Copy-PackageFile (Join-Path $workspaceRoot "Webots_Epuck_Introduction_and_Literature_Review.docx") "documents\Webots_Epuck_Introduction_and_Literature_Review.docx"
    Copy-PackageFile (Join-Path $workspaceRoot "Manikanta_Project_Changes(E-puck Changes).csv") "documents\Manikanta_Project_Changes(E-puck Changes).csv"

    foreach ($summary in @(
        "20260820_224341_129620_baseline_short.json",
        "20260820_225829_866703_transcriptions.json",
        "20260820_231254_095929_navigation_changes.json",
        "20260820_231550_507068_safety.json",
        "20260821_081648_987706_goto_a_shortest.json",
        "20260821_082452_048195_demo_showcase.json",
        "20260821_082533_130819_voice_stop.json",
        "20260821_082607_547454_head_shake.json",
        "20260821_082709_958481_blocked_corridor.json",
        "20260824_002905_892164_baseline_short.json"
        "20260824_021650_245838_baseline_short.json"
        "20260824_082011_814930_midroute_destination_change.json"
        "20260824_084455_900486_midroute_destination_change.json"
        "20260824_084958_555229_midroute_destination_change.json"
        "20260910_081439_582222_midroute_destination_change.json"
        "20260910_084155_498202_all.json"
        "20260911_164027_853916_all.json"
        "20260911_164339_451358_midroute_destination_change.json"
    )) {
        Copy-PackageFile (Join-Path $projectRoot "validation_runs\suite_summaries\$summary") "evidence\suite_summaries\$summary"
    }

    Copy-EvidenceRun "20260821_081724_847551_demo_showcase_01" "enlarged_robot_showcase"
    Copy-EvidenceRun "20260821_081534_128679_goto_a_shortest_01" "enlarged_robot_navigation"
    Copy-EvidenceRun "20260821_082510_748342_voice_stop_01" "voice_stop"
    Copy-EvidenceRun "20260821_082545_425154_head_shake_01" "head_shake"
    Copy-EvidenceRun "20260821_082620_319269_blocked_corridor_01" "blocked_corridor"
    Copy-EvidenceRun "20260824_002708_829928_baseline_short_01" "post_dashboard_baseline"
    Copy-EvidenceRun "20260824_021639_627551_baseline_short_01" "self_contained_asset_baseline"
    Copy-EvidenceRun "20260824_081946_273868_midroute_destination_change_01" "voice_destination_override"
    Copy-EvidenceRun "20260824_084444_744262_midroute_destination_change_01" "explicit_voice_camera_mode"
    Copy-EvidenceRun "20260824_084948_194303_midroute_destination_change_01" "final_voice_camera_vosk_regression"
    Copy-EvidenceRun "20260910_081415_575273_midroute_destination_change_01" "startup_motor_lock_regression"
    Copy-EvidenceRun "20260911_164332_358437_midroute_destination_change_03" "separate_voice_override_confirmation"
    Copy-EvidenceRun "20260824_024532_896682_gesture_video_control" "gesture_video_control"
    Copy-PackageFile (Join-Path $projectRoot "validation_runs\gesture_video_clip\tilt_analysis_final_verified.json") "evidence\gesture\tilt_analysis_final_verified.json"
    Copy-PackageFile (Join-Path $projectRoot "validation_runs\gesture_video_clip\tilt_analysis_dashboard_verified.json") "evidence\gesture\tilt_analysis_dashboard_verified.json"
    Copy-PackageFile (Join-Path $projectRoot "validation_runs\gesture_video_clip\traceability_dashboard_demo.json") "evidence\gesture\traceability_dashboard_demo.json"
    Copy-PackageFile (Join-Path $projectRoot "validation_runs\device_readiness\20260808_client_hardening_probe.json") "evidence\device_readiness\client_hardening_probe.json"
    Copy-PackageFile (Join-Path $projectRoot "validation_runs\client_device_preflight_20260824.json") "evidence\device_readiness\client_microphone_callback_probe_20260824.json"

    $evidenceReadme = @"
# Selected verification evidence

This folder contains non-identifying technical evidence selected from the full
development `validation_runs` directory. The full transient run history is not
required for submission.

- `suite_summaries/`: baseline, transcript, navigation, safety, rendered, and
  final enlarged-robot suite results.
- `runs/enlarged_robot_showcase/`: final rendered all-changes run, excluding the
  intermediate raw movie because the finished video is under `demo/`.
- `runs/enlarged_robot_navigation/`: rendered S-to-A visibility/navigation run.
- `runs/voice_stop/`, `runs/head_shake/`, and `runs/blocked_corridor/`: final
  rendered safety evidence.
- `runs/post_dashboard_baseline/`: passing Docker baseline after dashboard and
  Docker shared-memory hardening.
- `runs/self_contained_asset_baseline/`: fresh passing Docker baseline after
  packaging the Webots R2025a resources locally.
- `runs/voice_destination_override/`: passing Docker proof that START remains
  stationary and a microphone destination command replaces an active route
  after nod confirmation.
- `runs/explicit_voice_camera_mode/`: passing Docker proof of stationary START,
  Voice-to-Camera gesture handoff, Camera-to-Voice mid-route override, and the
  confirming Voice-to-Camera handoff before arrival at B.
- `runs/final_voice_camera_vosk_regression/`: final passing Webots regression
  from the same code that explicitly enables Vosk word-confidence output.
- `runs/startup_motor_lock_regression/`: passing post-fix evidence that the
  controller begins in IDLE, START is activation-only, and a separate
  destination plus nod is required before movement.
- `runs/gesture_video_control/`: passing rendered run driven by the exact
  production-classified gesture-video manifest; the intermediate raw movie is
  excluded because the synchronized professor copy is under `demo/`.
- `gesture/`: technical analysis of the supplied gesture clip; no frames or
  landmarks are retained, plus the consented derived-dashboard report. The raw
  source clip is not packaged.
- `device_readiness/`: non-recording device-readiness and microphone callback
  pipeline reports; no audio is stored.
- `client_audit/`: fresh Windows environment installation/test log and latest
  complete Docker regression log. Physical client devices remain unverified.
"@
    $evidenceReadmePath = Join-Path $stage "evidence\README.md"
    New-Item -ItemType Directory -Path (Split-Path -Parent $evidenceReadmePath) -Force | Out-Null
    [IO.File]::WriteAllText($evidenceReadmePath, $evidenceReadme, [Text.UTF8Encoding]::new($false))

    $manifestPath = Join-Path $stage "SHA256SUMS.txt"
    $manifestLines = foreach ($file in Get-ChildItem -LiteralPath $stage -Recurse -File | Sort-Object FullName) {
        if ($file.FullName -eq $manifestPath) {
            continue
        }
        $relative = (Get-RelativePathCompat $stage $file.FullName).Replace('\', '/')
        "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant(), $relative
    }
    [IO.File]::WriteAllLines($manifestPath, $manifestLines, [Text.UTF8Encoding]::new($false))

    Compress-Archive -LiteralPath (Get-ChildItem -LiteralPath $stage | ForEach-Object FullName) -DestinationPath $temporaryZip -CompressionLevel Optimal

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($temporaryZip)
    try {
        $entryNames = @($archive.Entries | Where-Object { -not [string]::IsNullOrEmpty($_.Name) } | ForEach-Object { $_.FullName.Replace('\', '/') })
        $entriesByNormalisedName = @{}
        foreach ($archiveEntry in $archive.Entries) {
            if (-not [string]::IsNullOrEmpty($archiveEntry.Name)) {
                $entriesByNormalisedName[$archiveEntry.FullName.Replace('\', '/')] = $archiveEntry
            }
        }
        $required = @(
            "AGENTS.md",
            "CLIENT_READINESS_AUDIT.md",
            "tools/setup_client.py",
            "CODE_EXPLANATION.md",
            "instructions.md",
            "PROJECT_CHANGES_CHECKLIST.md",
            "controllers/epuck_waypoint_controller/epuck_waypoint_controller.py",
            "controllers/epuck_waypoint_controller/model.py",
            "controllers/epuck_waypoint_controller/live_dashboard.py",
            "demo/head_gesture_video_controlled_robot.mp4",
            "documents/35056702_Documentation.docx",
            "documents/Webots_Epuck_Introduction_and_Literature_Review.docx",
            "models/vosk-model-small-en-us-0.15/am/final.mdl",
            "tests/test_expanded_navigation.py",
            "tests/test_live_dashboard.py",
            "tests/test_world_configuration.py",
            "tools/build_showcase_video.ps1",
            "tools/build_gesture_control_demo.ps1",
            "tools/build_gesture_control_sequence.py",
            "tools/build_trace_dashboard_demo.py",
            "tools/run_gesture_control_webots.py",
            "tools/build_submission_zip.ps1",
            "protos/vendor/epuck/E-puck.proto",
            "protos/vendor/epuck/E-puckDistanceSensor.proto",
            "protos/vendor/appearances/PorcelainChevronTiles.proto",
            "worlds/epuck_waypoint_navigation.wbt",
            "SHA256SUMS.txt"
        )
        foreach ($name in $required) {
            if ($name -notin $entryNames) {
                throw "Required ZIP entry is missing: $name"
            }
        }

        $worldEntries = @($entryNames | Where-Object { $_ -like "*.wbt" })
        if ($worldEntries.Count -ne 1 -or $worldEntries[0] -ne "worlds/epuck_waypoint_navigation.wbt") {
            throw "The package must contain exactly the main WBT world. Found: $($worldEntries -join ', ')"
        }

        $videoEntries = @($entryNames | Where-Object { $_ -like "*.mp4" })
        if ($videoEntries.Count -ne 1 -or $videoEntries[0] -ne "demo/head_gesture_video_controlled_robot.mp4") {
            throw "The package must contain only the latest face-blurred demonstration. Found: $($videoEntries -join ', ')"
        }

        $forbidden = @($entryNames | Where-Object {
            $_ -match '(^|/)(\.venv|validation_runs|__pycache__)(/|$)' -or
            $_ -match '\.pyc$|\.wbproj$' -or
            $_ -match '(^|/)head_gesture_car\.wbt$' -or
            $_ -match 'head_gesture_epuck_demo_for_professor|demo_raw\.mp4|tilt_gesture\.mp4'
        })
        if ($forbidden.Count) {
            throw "Forbidden entries found in submission: $($forbidden -join ', ')"
        }

        $manifestEntry = $archive.GetEntry("SHA256SUMS.txt")
        $reader = [IO.StreamReader]::new($manifestEntry.Open())
        try {
            $packagedManifest = $reader.ReadToEnd() -split "`r?`n" | Where-Object { $_ }
        }
        finally {
            $reader.Dispose()
        }
        if ($packagedManifest.Count -ne ($entryNames.Count - 1)) {
            throw "Checksum manifest count does not match packaged file count."
        }
        foreach ($line in $packagedManifest) {
            if ($line -notmatch '^([0-9a-f]{64})  (.+)$') {
                throw "Invalid checksum line: $line"
            }
            $expectedHash = $Matches[1]
            $name = $Matches[2]
            $entry = $entriesByNormalisedName[$name]
            if (-not $entry) {
                throw "Checksum entry is absent from ZIP: $name"
            }
            $stream = $entry.Open()
            try {
                $actualHash = Get-StreamSha256 $stream
            }
            finally {
                $stream.Dispose()
            }
            if ($actualHash -ne $expectedHash) {
                throw "Checksum mismatch for ZIP entry: $name"
            }
        }
    }
    finally {
        $archive.Dispose()
    }

    New-Item -ItemType Directory -Path $qa | Out-Null
    Expand-Archive -LiteralPath $temporaryZip -DestinationPath $qa
    $python = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        $python = "python"
    }
    Push-Location $qa
    try {
        $savedErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $python -m unittest discover -s tests -v 2>&1 | Tee-Object -Variable extractedTestOutput
        $extractedTestExitCode = $LASTEXITCODE
        $ErrorActionPreference = $savedErrorActionPreference
        if ($extractedTestExitCode -ne 0) {
            throw "Offline tests failed from the extracted submission package."
        }
    }
    finally {
        if ($savedErrorActionPreference) {
            $ErrorActionPreference = $savedErrorActionPreference
        }
        Pop-Location
    }

    foreach ($finalVideo in @("head_gesture_video_controlled_robot.mp4")) {
        $sourceVideoHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $projectRoot "demo\$finalVideo")).Hash
        $extractedVideoHash = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $qa "demo\$finalVideo")).Hash
        if ($sourceVideoHash -ne $extractedVideoHash) {
            throw "Final video changed while packaging: $finalVideo"
        }
    }

    $previousHash = if (Test-Path -LiteralPath $destinationPath -PathType Leaf) {
        (Get-FileHash -Algorithm SHA256 -LiteralPath $destinationPath).Hash
    }
    else {
        "<none>"
    }
    Move-Item -LiteralPath $temporaryZip -Destination $destinationPath -Force
    $finalHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destinationPath).Hash
    $finalItem = Get-Item -LiteralPath $destinationPath
    Write-Output "Submission ZIP updated: $destinationPath"
    Write-Output "Previous SHA256: $previousHash"
    Write-Output "Final SHA256: $finalHash"
    Write-Output "ZIP size: $($finalItem.Length) bytes"
    Write-Output "Packaged files: $($manifestLines.Count + 1)"
    Write-Output "Extracted offline tests: passed"
}
finally {
    if (Test-Path -LiteralPath $stage) {
        Assert-TemporaryPath $stage "_submission_stage_"
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
    if (Test-Path -LiteralPath $qa) {
        Assert-TemporaryPath $qa "_submission_qa_"
        Remove-Item -LiteralPath $qa -Recurse -Force
    }
    if (Test-Path -LiteralPath $temporaryZip) {
        Assert-TemporaryPath $temporaryZip "_submission_archive_"
        Remove-Item -LiteralPath $temporaryZip -Force
    }
}
