<#
    build.ps1 -- build and install the dark theme for TIM 3.5.0.22149.

    Typical use
    -----------
        .\build.ps1 -Backup            # once: save the pristine .rdb files
        .\build.ps1 -Install           # build, install, clear TIM's cache, restart
        .\build.ps1 -Rollback          # restore everything (rdb + DLLs)

    Every step is idempotent: the sources are always re-extracted from the
    pristine backups, so a build never compounds on a previous one.
#>
param(
    [string]$TimDir = "C:\software\TIM",
    [string]$Work    = "",              # defaults to this script's directory
    [switch]$Backup,
    [switch]$Install,
    [switch]$Rollback,
    [switch]$NoRestart,
    [switch]$SkipDllPatch
)
$ErrorActionPreference = "Stop"

$py = if ($env:TIMDARK_PYTHON) { $env:TIMDARK_PYTHON } else { "python" }
if (-not $Work) { $Work = $PSScriptRoot }
$tools  = Join-Path $Work "tools"
$srcD   = Join-Path $Work "src"
$outD   = Join-Path $Work "out"
$bakD   = Join-Path $Work "backup"
$resDir = Join-Path $TimDir "Resource.3.5.0.22149"
$binDir = Join-Path $TimDir "Bin"
$env:PYTHONWARNINGS = "ignore"

function Stop-Tim {
    Get-Process TIM -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() | Out-Null }
    Start-Sleep -Seconds 3
    Get-CimInstance Win32_Process -Filter "Name='TIM.exe'" -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 3
    Get-CimInstance Win32_Process -Filter "Name='TIM.exe'" -ErrorAction SilentlyContinue |
        ForEach-Object { taskkill /F /PID $_.ProcessId 2>&1 | Out-Null }
    Start-Sleep -Seconds 2
    Write-Host ("TIM stopped: {0} left" -f @(Get-Process TIM -ErrorAction SilentlyContinue).Count)
}

function Start-Tim {
    $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "TIM.lnk"
    if (Test-Path $lnk) { Start-Process $lnk } else { Start-Process (Join-Path $binDir "TIM.exe") }
    Start-Sleep -Seconds 22
}

# TIM caches extracted resource text (theme.xml among it) in a zlib blob called
# rdo.cache and does NOT refresh it when the .rdb changes.  A stale cache
# silently keeps the ORIGINAL theme colours, so every install must drop it.
function Clear-TimCache {
    $ts = Get-Date -Format "yyyyMMdd-HHmmss"
    foreach ($f in @("rdo.cache", "loginrdo.cache")) {
        $p = Join-Path $env:APPDATA "Tencent\TIM\$f"
        if (Test-Path $p) { Move-Item $p "$p.bak-$ts" -Force; Write-Host "  cleared $f" }
    }
}

# --------------------------------------------------------------------- backup
if ($Backup) {
    New-Item -ItemType Directory -Force -Path $bakD | Out-Null
    $map = @{ "Res.rdb" = "Res.rdb.orig"; "Xtml.rdb" = "Xtml.rdb.orig"
              "Data.rdb" = "Data.rdb.orig"; "Themes\Default.rdb" = "Default.rdb.orig" }
    foreach ($k in $map.Keys) {
        $from = Join-Path $resDir $k
        $to   = Join-Path $bakD $map[$k]
        if ((Test-Path $from) -and -not (Test-Path $to)) {
            Copy-Item $from $to -Force
            Write-Host "  backed up $k"
        }
    }
    Write-Host "backup complete"
    return
}

# ------------------------------------------------------------------- rollback
if ($Rollback) {
    Stop-Tim
    foreach ($pair in @(@("Res.rdb","Res.rdb.orig"), @("Themes\Default.rdb","Default.rdb.orig"),
                        @("Data.rdb","Data.rdb.orig"), @("Xtml.rdb","Xtml.rdb.orig"))) {
        $b = Join-Path $bakD $pair[1]
        if (Test-Path $b) { Copy-Item $b (Join-Path $resDir $pair[0]) -Force }
    }
    & $py (Join-Path $tools "patch_dll.py") --tim-dir $TimDir --revert
    Write-Host "rolled back"
    if (-not $NoRestart) { Start-Tim }
    return
}

# ---------------------------------------------------------------------- build
foreach ($pair in @(@("Res","Res.rdb.orig"), @("Default","Default.rdb.orig"), @("Xtml","Xtml.rdb.orig"))) {
    $dir = Join-Path $srcD $pair[0]
    Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    & $py (Join-Path $tools "rdb.py") unpack (Join-Path $bakD $pair[1]) $dir | Out-Null
}
Write-Host "re-extracted pristine sources"

& $py (Join-Path $tools "makedark.py")  (Join-Path $srcD "Default\appframework\config\theme.xml")
& $py (Join-Path $tools "skinpatch.py") apply (Join-Path $srcD "Default") | Select-Object -Last 1
& $py (Join-Path $tools "skinpatch.py") apply (Join-Path $srcD "Res")     | Select-Object -Last 1
& $py (Join-Path $tools "gmdark.py")    (Join-Path $srcD "Default")       | Select-Object -Last 1
& $py (Join-Path $tools "gmdark.py")    (Join-Path $srcD "Xtml")          | Select-Object -Last 1

New-Item -ItemType Directory -Force -Path $outD | Out-Null
& $py (Join-Path $tools "rdb.py") pack (Join-Path $srcD "Default") (Join-Path $outD "Default.rdb") --manifest (Join-Path $bakD "Default.rdb.orig")
& $py (Join-Path $tools "rdb.py") pack (Join-Path $srcD "Res")     (Join-Path $outD "Res.rdb")     --manifest (Join-Path $bakD "Res.rdb.orig")
& $py (Join-Path $tools "rdb.py") pack (Join-Path $srcD "Xtml")    (Join-Path $outD "Xtml.rdb")    --manifest (Join-Path $bakD "Xtml.rdb.orig")

# -------------------------------------------------------------------- install
if ($Install) {
    Stop-Tim
    Copy-Item (Join-Path $outD "Default.rdb") (Join-Path $resDir "Themes\Default.rdb") -Force
    Copy-Item (Join-Path $outD "Res.rdb")     (Join-Path $resDir "Res.rdb")            -Force
    Copy-Item (Join-Path $outD "Xtml.rdb")    (Join-Path $resDir "Xtml.rdb")           -Force
    Write-Host "installed resources"

    if (-not $SkipDllPatch) {
        # the two engine patches that turn the code-driven black text white
        & $py (Join-Path $tools "patch_dll.py") --tim-dir $TimDir --apply
    }

    Clear-TimCache
    if (-not $NoRestart) { Start-Tim }
}
