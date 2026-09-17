param(
    [string]$RunDirectory,
    [string]$DashboardVideo = "demo\gesture_video_control_dashboard.mp4",
    [string]$Output = "demo\head_gesture_video_controlled_robot.mp4"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path

function Get-VideoDuration([string]$Path) {
    $value = (& ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 $Path).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $value) { throw "Could not measure video duration: $Path" }
    return [double]::Parse($value, [Globalization.CultureInfo]::InvariantCulture)
}

function Format-AssTime([double]$Seconds) {
    if ($Seconds -lt 0) { $Seconds = 0 }
    $hours = [Math]::Floor($Seconds / 3600)
    $minutes = [Math]::Floor(($Seconds % 3600) / 60)
    $wholeSeconds = [Math]::Floor($Seconds % 60)
    $centiseconds = [Math]::Floor(($Seconds - [Math]::Floor($Seconds)) * 100)
    return ("{0}:{1:00}:{2:00}.{3:00}" -f $hours, $minutes, $wholeSeconds, $centiseconds)
}

if (-not $RunDirectory) {
    $run = Get-ChildItem -LiteralPath (Join-Path $projectRoot "validation_runs") -Directory |
        Where-Object {
            $_.Name -like "*_gesture_video_control" -and
            (Test-Path -LiteralPath (Join-Path $_.FullName "gesture_control_webots_raw.mp4")) -and
            (Test-Path -LiteralPath (Join-Path $_.FullName "integration_verification.json"))
        } |
        Sort-Object LastWriteTime |
        Where-Object {
            $candidate = Get-Content -LiteralPath (Join-Path $_.FullName "integration_verification.json") -Raw | ConvertFrom-Json
            $candidate.passed -and $candidate.staged_order_verified
        } |
        Select-Object -Last 1
    if (-not $run) { throw "No passing staged rendered gesture-video control run was found." }
    $RunDirectory = $run.FullName
}

$RunDirectory = (Resolve-Path -LiteralPath $RunDirectory).Path
$rawVideo = Join-Path $RunDirectory "gesture_control_webots_raw.mp4"
$DashboardVideo = if ([IO.Path]::IsPathRooted($DashboardVideo)) { $DashboardVideo } else { Join-Path $projectRoot $DashboardVideo }
$DashboardVideo = (Resolve-Path -LiteralPath $DashboardVideo).Path
$Output = if ([IO.Path]::IsPathRooted($Output)) { $Output } else { Join-Path $projectRoot $Output }
$verification = Get-Content -LiteralPath (Join-Path $RunDirectory "integration_verification.json") -Raw | ConvertFrom-Json
if (-not $verification.passed -or -not $verification.staged_order_verified -or $verification.final_state -ne "STOPPED") {
    throw "The selected Webots replay did not prove the staged command order and STOPPED state."
}

$rawDuration = Get-VideoDuration $rawVideo
$dashboardDuration = Get-VideoDuration $DashboardVideo
$speedRatio = $rawDuration / $dashboardDuration
$ratioText = $speedRatio.ToString("0.########", [Globalization.CultureInfo]::InvariantCulture)
$endAss = Format-AssTime $rawDuration

$captions = @(
    @(0.0, 2.0, "Neutral calibration - robot stays at S"),
    @(2.0, 3.56, "Text-only fixture: START A - awaiting route gesture"),
    @(3.56, 6.96, "LEFT TILT selects shortest S to A; NOD confirms"),
    @(6.96, 58.0, "COMMAND 1 RUNNING - wait until the robot reaches A"),
    @(58.0, 59.96, "A REACHED - text-only fixture: GO TO C"),
    @(59.96, 63.60, "LEFT TILT selects shortest A to C; NOD confirms"),
    @(63.60, 108.0, "COMMAND 2 RUNNING - wait until the robot reaches C"),
    @(108.0, 109.48, "C REACHED - text-only fixture: GO TO B"),
    @(109.48, 112.64, "RIGHT TILT selects alternate C to B; NOD confirms"),
    @(112.64, 130.20, "COMMAND 3 RUNNING - robot moves toward B"),
    @(130.20, 131.32, "HEAD SHAKE INTERRUPTS COMMAND 3 - motors STOPPED")
)

$eventLines = [Collections.Generic.List[string]]::new()
$eventLines.Add("Dialogue: 0,0:00:00.00,$endAss,Pane,,0,0,0,,{\an8\pos(320,24)}LIVE GESTURE INPUT + TRACE DASHBOARD")
$eventLines.Add("Dialogue: 0,0:00:00.00,$endAss,Pane,,0,0,0,,{\an8\pos(960,24)}ACTUAL WEBOTS ROBOT OUTPUT")
foreach ($caption in $captions) {
    $start = Format-AssTime ([double]$caption[0] * $speedRatio)
    $end = Format-AssTime ([Math]::Min([double]$caption[1] * $speedRatio, $rawDuration))
    $eventLines.Add("Dialogue: 0,$start,$end,Action,,0,0,0,,$($caption[2])")
}

$buildDir = Join-Path $projectRoot "demo\_gesture_control_build"
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$assPath = Join-Path $buildDir "gesture_control.ass"
$assHeader = @"
[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Pane,Arial,25,&H00FFFFFF,&H000000FF,&H00101010,&HC0000000,-1,0,0,0,100,100,0,0,3,1,0,8,25,25,18,1
Style: Action,Arial,25,&H00FFFFFF,&H000000FF,&H00101010,&HD0000000,-1,0,0,0,100,100,0,0,3,1,0,2,45,45,22,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"@
[IO.File]::WriteAllText($assPath, $assHeader + "`n" + ($eventLines -join "`n") + "`n", [Text.UTF8Encoding]::new($false))

$filterAss = $assPath.Replace('\', '/').Replace(':', '\:')
$filter = "[0:v]trim=start=0:end=$dashboardDuration,setpts=$ratioText*PTS,fps=25,scale=640:380:force_original_aspect_ratio=decrease,pad=640:720:(ow-iw)/2:(oh-ih)/2:color=0x171A20,setsar=1[dashboard];[1:v]trim=start=0:end=$rawDuration,setpts=PTS-STARTPTS,fps=25,crop=640:720:320:0,setsar=1[robot];[dashboard][robot]hstack=inputs=2,drawbox=x=637:y=0:w=6:h=720:color=0xD8DEE9@0.90:t=fill,ass='$filterAss'[composed];[composed]split[privacy_base][privacy_source];[privacy_source]crop=135:120:100:230,boxblur=18:4[blurred_face];[privacy_base][blurred_face]overlay=100:230[outv]"

& ffmpeg -y -v error -i $DashboardVideo -i $rawVideo -filter_complex $filter -map "[outv]" -an -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 25 -movflags +faststart $Output
if ($LASTEXITCODE -ne 0) { throw "Failed to build synchronized gesture-control demonstration." }

$thumbnail = Join-Path $projectRoot "demo\head_gesture_video_controlled_robot_thumbnail.jpg"
$contact = Join-Path $projectRoot "demo\head_gesture_video_controlled_robot_contact_sheet.jpg"
$thumbnailAt = ($rawDuration * 0.86).ToString("0.###", [Globalization.CultureInfo]::InvariantCulture)
$contactRate = (5.0 / $rawDuration).ToString("0.########", [Globalization.CultureInfo]::InvariantCulture)
& ffmpeg -y -v error -ss $thumbnailAt -i $Output -frames:v 1 $thumbnail
if ($LASTEXITCODE -ne 0) { throw "Failed to build gesture-control thumbnail." }
& ffmpeg -y -v error -i $Output -vf "fps=$contactRate,scale=320:180,tile=5x1" -frames:v 1 $contact
if ($LASTEXITCODE -ne 0) { throw "Failed to build gesture-control contact sheet." }

$buildReport = [ordered]@{
    output = (Resolve-Path -LiteralPath $Output).Path
    run_directory = $RunDirectory
    dashboard_duration_seconds = [Math]::Round($dashboardDuration, 3)
    webots_duration_seconds = [Math]::Round($rawDuration, 3)
    dashboard_speed_ratio = [Math]::Round($speedRatio, 6)
    staged_order_verified = [bool]$verification.staged_order_verified
    subject_face_blurred = $true
    route_starts = @($verification.route_starts)
    final_state = $verification.final_state
}
$buildReport | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $buildDir "build_report.json") -Encoding utf8

Write-Output $Output
Write-Output $thumbnail
Write-Output $contact
