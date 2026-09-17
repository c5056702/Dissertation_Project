param(
    [string]$Scenario = "baseline_short",
    [ValidateRange(1, 100)]
    [int]$Repeat = 1,
    [switch]$Visible,
    [switch]$RecordDemo
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$composeFile = Join-Path $projectRoot "compose.webots.yaml"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker was not found on PATH. Start Docker Desktop and try again."
}

$validationArguments = @(
    "compose", "-f", $composeFile,
    "run", "--rm", "webots-validation",
    "python3", "tools/run_validation.py",
    "--scenario", $Scenario,
    "--repeat", $Repeat
)
if ($Visible) {
    $validationArguments += "--visible"
}
if ($RecordDemo) {
    $validationArguments += "--record-demo"
}

Push-Location $projectRoot
$dockerExitCode = 1
try {
    # Windows PowerShell surfaces ordinary Docker stderr progress as a
    # NativeCommandError when Stop is active. Docker's exit code remains the
    # authoritative result for this wrapper.
    $ErrorActionPreference = "Continue"
    & docker @validationArguments
    $dockerExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $dockerExitCode
