$ErrorActionPreference = "Stop"

$repoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$entries = @()
if ($userPath) {
    $entries = $userPath -split ';' | Where-Object { $_ -ne "" }
}

$alreadyInstalled = $entries | Where-Object {
    try {
        [IO.Path]::GetFullPath($_).TrimEnd('\') -ieq [IO.Path]::GetFullPath($repoDir).TrimEnd('\')
    } catch {
        $_ -ieq $repoDir
    }
}

if (-not $alreadyInstalled) {
    $newPath = (@($entries) + $repoDir) -join ';'
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$env:Path;$repoDir"
    Write-Host "Added to user PATH: $repoDir"
} else {
    Write-Host "Already in user PATH: $repoDir"
}

$psEntry = Join-Path $repoDir "localagentskills.ps1"
$shim = @"
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "$psEntry" %*
exit /b %ERRORLEVEL%
"@

$shimDirs = @(
    (Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"),
    (Join-Path $env:USERPROFILE ".claude\bin")
)

foreach ($shimDir in $shimDirs) {
    if (-not (Test-Path $shimDir)) {
        New-Item -ItemType Directory -Path $shimDir -Force | Out-Null
    }
    $shimPath = Join-Path $shimDir "localagentskills.cmd"
    Set-Content -LiteralPath $shimPath -Value $shim -Encoding ASCII
    Write-Host "Installed command shim: $shimPath"
}

Write-Host ""
Write-Host "Run:"
Write-Host "  localagentskills list"
Write-Host ""
Write-Host "If the current shell still cannot see it, reopen PowerShell."
