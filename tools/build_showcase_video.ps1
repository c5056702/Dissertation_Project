param(
    [string]$RawVideo,
    [string]$DashboardVideo = "demo\traceability_dashboard_demo.mp4",
    [string]$Output = "demo\head_gesture_epuck_all_changes_showcase.mp4"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$demoDir = Join-Path $projectRoot "demo"
$buildDir = Join-Path $demoDir "_showcase_build"
New-Item -ItemType Directory -Path $buildDir -Force | Out-Null

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "ffmpeg is required to build the showcase video."
}

function Get-LatestRun([string]$pattern, [string]$requiredFile) {
    $candidate = Get-ChildItem -LiteralPath (Join-Path $projectRoot "validation_runs") -Directory |
        Where-Object { $_.Name -like $pattern -and (Test-Path -LiteralPath (Join-Path $_.FullName $requiredFile)) } |
        Sort-Object LastWriteTime |
        Select-Object -Last 1
    if (-not $candidate) {
        throw "No validation run matching $pattern contains $requiredFile."
    }
    return $candidate.FullName
}

if (-not $RawVideo) {
    $showcaseRun = Get-LatestRun "*_demo_showcase_01" "demo_raw.mp4"
    $RawVideo = Join-Path $showcaseRun "demo_raw.mp4"
}
$RawVideo = (Resolve-Path -LiteralPath $RawVideo).Path
$DashboardVideo = if ([IO.Path]::IsPathRooted($DashboardVideo)) { $DashboardVideo } else { Join-Path $projectRoot $DashboardVideo }
$DashboardVideo = (Resolve-Path -LiteralPath $DashboardVideo).Path

$showcaseRunDir = Split-Path -Parent $RawVideo
$initialImage = Join-Path $showcaseRunDir "screenshots\00_initial_overview.jpg"
$voiceRun = Get-LatestRun "*_voice_stop_01" "screenshots\safety_stop_voice.jpg"
$shakeRun = Get-LatestRun "*_head_shake_01" "screenshots\safety_stop_head_shake.jpg"
$obstacleRun = Get-LatestRun "*_blocked_corridor_01" "screenshots\safety_stop_obstacle.jpg"
$voiceImage = Join-Path $voiceRun "screenshots\safety_stop_voice.jpg"
$shakeImage = Join-Path $shakeRun "screenshots\safety_stop_head_shake.jpg"
$obstacleImage = Join-Path $obstacleRun "screenshots\safety_stop_obstacle.jpg"

foreach ($required in ($initialImage, $voiceImage, $shakeImage, $obstacleImage)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required showcase evidence is missing: $required"
    }
}

function Write-Utf8NoBom([string]$path, [string]$content) {
    [IO.File]::WriteAllText($path, $content, [Text.UTF8Encoding]::new($false))
}

function Convert-ToFilterPath([string]$path) {
    return ($path.Replace('\', '/').Replace(':', '\:'))
}

$assHeader = @"
[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Banner,Arial,28,&H00FFFFFF,&H000000FF,&H00101010,&HC0000000,-1,0,0,0,100,100,0,0,3,1,0,2,45,45,24,1
Style: Title,Arial,48,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,3,1,0,5,70,70,20,1
Style: CardTitle,Arial,38,&H0000D7FF,&H000000FF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,3,1,0,8,70,70,66,1
Style: CardBody,Arial,27,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,0,0,0,0,100,100,0,0,3,1,0,7,85,85,125,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"@

$introAss = $assHeader + "`r`n" + @"
Dialogue: 0,0:00:00.00,0:00:05.00,Title,,0,0,0,,Multimodal e-puck Navigation\NAll Requested Changes Showcase
Dialogue: 0,0:00:02.10,0:00:05.00,Banner,,0,0,0,,Webots R2025a • local multimodal input • consented traceability demonstration
"@

$mainAss = $assHeader + "`r`n" + @"
Dialogue: 0,0:00:00.00,0:00:02.50,Banner,,0,0,0,,START activates the controller; the e-puck never moves automatically
Dialogue: 0,0:00:02.50,0:00:06.00,Banner,,0,0,0,,GO TO A + right tilt + nod: compute and confirm an alternative route
Dialogue: 0,0:00:06.00,0:00:11.00,Banner,,0,0,0,,RIGHT pauses safely; CONTINUE resumes the same autonomous route
Dialogue: 0,0:00:11.00,0:00:16.00,Banner,,0,0,0,,No coloured floor paths: GPS, compass and internal waypoints control movement
Dialogue: 0,0:00:16.00,0:00:22.00,Banner,,0,0,0,,GO TO B then ALTERNATIVE ROUTE: stop and replan from the measured pose
Dialogue: 0,0:00:22.00,0:00:38.00,Banner,,0,0,0,,The graph selects a distinct collision-free route; proximity safety stays active
Dialogue: 0,0:00:38.00,0:00:44.00,Banner,,0,0,0,,GO TO C, then GO TO S mid-route: destination replacement requires a nod
Dialogue: 0,0:00:44.00,0:00:54.00,Banner,,0,0,0,,A new shortest route starts from the live GPS position—not from the old route start
Dialogue: 0,0:00:54.00,0:00:58.00,Banner,,0,0,0,,GO TO A starts the shortest route from S
Dialogue: 0,0:00:58.00,0:01:01.00,Banner,,0,0,0,,REVERSE + nod replans to the active route origin and returns to S
"@

$safetyAss = $assHeader + "`r`n" + @"
Dialogue: 0,0:00:00.00,0:00:04.00,Banner,,0,0,0,,Voice STOP has highest priority: motors stop and state becomes STOPPED
Dialogue: 0,0:00:04.00,0:00:08.00,Banner,,0,0,0,,Head shake is an independent immediate cancel/stop action
Dialogue: 0,0:00:08.00,0:00:12.00,Banner,,0,0,0,,A blocked corridor triggers proximity-sensor stopping before collision
"@

$summaryAss = $assHeader + "`r`n" + @"
Dialogue: 0,0:00:00.00,0:00:05.00,CardTitle,,0,0,0,,WORLD, VISIBILITY AND ACTIVATION
Dialogue: 0,0:00:00.00,0:00:05.00,CardBody,,0,0,0,,1  No automatic movement • 2  Enlarged visible e-puck + locator\N3  Coloured route tracks removed completely • 5  START activation\N13  Command/state overlay • 17  Destination and current-position indicators
Dialogue: 0,0:00:05.00,0:00:10.00,CardTitle,,0,0,0,,ROUTING AND INTERVENTION
Dialogue: 0,0:00:05.00,0:00:10.00,CardBody,,0,0,0,,6  All waypoint combinations • 7  GO TO A/B/C/S\N8  Mid-route clarification • 9  Current-position replanning\N14  Stop and wait on arrival • 18  Shortest/alternative graph paths\N19  Validated corridors • 21  Bounded commands • 22  Safe intervention
Dialogue: 0,0:00:10.00,0:00:15.00,CardTitle,,0,0,0,,MULTIMODAL CONTROL AND SAFETY
Dialogue: 0,0:00:10.00,0:00:15.00,CardBody,,0,0,0,,4 and 23  Voice + gestures active together • 10  STOP priority\N11  IDLE/READY/NAVIGATING/PAUSED/ARRIVED/STOPPED states\N12  Calibration, thresholds, hold, smoothing and cooldown\N15  Invalid commands cannot move • 16  Deterministic conflict priority\N20  ps0–ps7 obstacle supervision
Dialogue: 0,0:00:15.00,0:00:20.00,CardTitle,,0,0,0,,LOCAL PROCESSING, LOGGING AND EVIDENCE
Dialogue: 0,0:00:15.00,0:00:20.00,CardBody,,0,0,0,,24  Accepted/rejected commands, gestures, timing, routes and outcomes logged\NLocal Vosk + MediaPipe; no cloud/LLM and no runtime recording/landmarks\NSplit-screen robot view + live camera, decisions, route, safety, events, STOP and RESET\N56/56 offline tests • 12/12 navigation • 16/16 safety • 5/5 transcripts
"@

$splitAss = $assHeader + "`r`n" + @"
Dialogue: 0,0:00:00.00,0:00:28.00,Banner,,0,0,0,,{\an8\pos(320,25)}LIVE CONTROL DASHBOARD
Dialogue: 0,0:00:00.00,0:00:28.00,Banner,,0,0,0,,{\an8\pos(960,25)}WEBOTS ROBOT AND WORLD
"@

$introAssPath = Join-Path $buildDir "intro.ass"
$mainAssPath = Join-Path $buildDir "main.ass"
$safetyAssPath = Join-Path $buildDir "safety.ass"
$summaryAssPath = Join-Path $buildDir "summary.ass"
$splitAssPath = Join-Path $buildDir "split_screen.ass"
Write-Utf8NoBom $introAssPath $introAss
Write-Utf8NoBom $mainAssPath $mainAss
Write-Utf8NoBom $safetyAssPath $safetyAss
Write-Utf8NoBom $summaryAssPath $summaryAss
Write-Utf8NoBom $splitAssPath $splitAss

$intro = Join-Path $buildDir "01_intro.mp4"
$dashboardSegment = Join-Path $buildDir "02_dashboard.mp4"
$main = Join-Path $buildDir "02_main.mp4"
$safety = Join-Path $buildDir "03_safety.mp4"
$summary = Join-Path $buildDir "04_summary.mp4"

$commonEncode = @("-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-r", "25")

& ffmpeg -y -v error -loop 1 -framerate 25 -t 5 -i $initialImage -vf "scale=1280:720,gblur=sigma=8,eq=brightness=-0.42,ass='$(Convert-ToFilterPath $introAssPath)'" @commonEncode $intro
if ($LASTEXITCODE -ne 0) { throw "Failed to build intro segment." }

$splitAssFilterPath = Convert-ToFilterPath $splitAssPath
$dashboardFilter = "[0:v]trim=start=0:end=18,setpts=PTS-STARTPTS,fps=25[d0];[0:v]trim=start=23:end=33,setpts=PTS-STARTPTS,fps=25[d1];[d0][d1]concat=n=2:v=1:a=0,scale=640:380:force_original_aspect_ratio=decrease,pad=640:720:(ow-iw)/2:(oh-ih)/2:color=0x171A20,setsar=1[dashboard];[1:v]trim=start=0:end=28,setpts=PTS-STARTPTS,fps=25,crop=640:720:320:0,setsar=1[robot];[dashboard][robot]hstack=inputs=2,drawbox=x=637:y=0:w=6:h=720:color=0xD8DEE9@0.90:t=fill,ass='$splitAssFilterPath'[outv]"
& ffmpeg -y -v error -i $DashboardVideo -i $RawVideo -filter_complex $dashboardFilter -map "[outv]" @commonEncode $dashboardSegment
if ($LASTEXITCODE -ne 0) { throw "Failed to build dashboard traceability segment." }

& ffmpeg -y -v error -i $RawVideo -vf "scale=1280:720,ass='$(Convert-ToFilterPath $mainAssPath)'" @commonEncode $main
if ($LASTEXITCODE -ne 0) { throw "Failed to caption main Webots segment." }

$safetyFilter = "[0:v]scale=1280:720,setsar=1[v0];[1:v]scale=1280:720,setsar=1[v1];[2:v]scale=1280:720,setsar=1[v2];[v0][v1][v2]concat=n=3:v=1:a=0,ass='$(Convert-ToFilterPath $safetyAssPath)'[outv]"
& ffmpeg -y -v error -loop 1 -framerate 25 -t 4 -i $voiceImage -loop 1 -framerate 25 -t 4 -i $shakeImage -loop 1 -framerate 25 -t 4 -i $obstacleImage -filter_complex $safetyFilter -map "[outv]" @commonEncode $safety
if ($LASTEXITCODE -ne 0) { throw "Failed to build safety segment." }

& ffmpeg -y -v error -loop 1 -framerate 25 -t 20 -i $initialImage -vf "scale=1280:720,gblur=sigma=14,eq=brightness=-0.50,ass='$(Convert-ToFilterPath $summaryAssPath)'" @commonEncode $summary
if ($LASTEXITCODE -ne 0) { throw "Failed to build summary segment." }

$concatList = Join-Path $buildDir "segments.txt"
$concatText = @($intro, $dashboardSegment, $main, $safety, $summary) | ForEach-Object { "file '$($_.Replace('\', '/'))'" }
Write-Utf8NoBom $concatList ($concatText -join "`n")

$outputPath = if ([IO.Path]::IsPathRooted($Output)) { $Output } else { Join-Path $projectRoot $Output }
& ffmpeg -y -v error -f concat -safe 0 -i $concatList -an -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -movflags +faststart $outputPath
if ($LASTEXITCODE -ne 0) { throw "Failed to assemble final showcase video." }

$thumbnail = Join-Path $demoDir "head_gesture_epuck_all_changes_showcase_thumbnail.jpg"
$contactSheet = Join-Path $demoDir "head_gesture_epuck_all_changes_showcase_contact_sheet.jpg"
& ffmpeg -y -v error -ss 18 -i $outputPath -frames:v 1 $thumbnail
if ($LASTEXITCODE -ne 0) { throw "Failed to generate showcase thumbnail." }
& ffmpeg -y -v error -i $outputPath -vf "fps=1/12,scale=320:180,tile=4x2" -frames:v 1 $contactSheet
if ($LASTEXITCODE -ne 0) { throw "Failed to generate showcase contact sheet." }

Write-Output $outputPath
Write-Output $thumbnail
Write-Output $contactSheet
