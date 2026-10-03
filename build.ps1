<#
    build.ps1 —— 构建并安装 TIM 3.5.0.22149 的深色主题。

    典型用法
    --------
        .\build.ps1 -Backup            # 首次执行：备份 TIM 原始的 .rdb
        .\build.ps1 -Install           # 构建 → 安装 → 打 DLL 补丁 → 清缓存 → 重启
        .\build.ps1 -Rollback          # 全部还原（资源 + 两个 DLL）

    每一步都是幂等的：源文件永远从备份重新解包，所以多次构建不会互相叠加。
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
    Write-Host ("TIM 已停止，剩余进程数: {0}" -f @(Get-Process TIM -ErrorAction SilentlyContinue).Count)
}

function Start-Tim {
    $lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "TIM.lnk"
    if (Test-Path $lnk) { Start-Process $lnk } else { Start-Process (Join-Path $binDir "TIM.exe") }
    Start-Sleep -Seconds 22
}

# TIM 会把解出来的资源文本（包括 theme.xml）缓存进一个叫 rdo.cache 的 zlib 块里，
# 而且改了 .rdb 之后它**不会刷新**。那份过期缓存会静默地让原始主题色继续生效，
# 所以每次装完都必须把它清掉。
function Clear-TimCache {
    $ts = Get-Date -Format "yyyyMMdd-HHmmss"
    foreach ($f in @("rdo.cache", "loginrdo.cache")) {
        $p = Join-Path $env:APPDATA "Tencent\TIM\$f"
        if (Test-Path $p) { Move-Item $p "$p.bak-$ts" -Force; Write-Host "  已清缓存 $f" }
    }
}

# --------------------------------------------------------------------- 备份
if ($Backup) {
    New-Item -ItemType Directory -Force -Path $bakD | Out-Null
    $map = @{ "Res.rdb" = "Res.rdb.orig"; "Xtml.rdb" = "Xtml.rdb.orig"
              "Data.rdb" = "Data.rdb.orig"; "Themes\Default.rdb" = "Default.rdb.orig" }
    foreach ($k in $map.Keys) {
        $from = Join-Path $resDir $k
        $to   = Join-Path $bakD $map[$k]
        if ((Test-Path $from) -and -not (Test-Path $to)) {
            Copy-Item $from $to -Force
            Write-Host "  已备份 $k"
        }
    }
    Write-Host "备份完成"
    return
}

# ------------------------------------------------------------------- 回滚
if ($Rollback) {
    Stop-Tim
    foreach ($pair in @(@("Res.rdb","Res.rdb.orig"), @("Themes\Default.rdb","Default.rdb.orig"),
                        @("Data.rdb","Data.rdb.orig"), @("Xtml.rdb","Xtml.rdb.orig"))) {
        $b = Join-Path $bakD $pair[1]
        if (Test-Path $b) { Copy-Item $b (Join-Path $resDir $pair[0]) -Force }
    }
    & $py (Join-Path $tools "patch_dll.py") --tim-dir $TimDir --revert
    Write-Host "已全部还原"
    if (-not $NoRestart) { Start-Tim }
    return
}

# ---------------------------------------------------------------------- 构建
foreach ($pair in @(@("Res","Res.rdb.orig"), @("Default","Default.rdb.orig"), @("Xtml","Xtml.rdb.orig"))) {
    $dir = Join-Path $srcD $pair[0]
    Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    & $py (Join-Path $tools "rdb.py") unpack (Join-Path $bakD $pair[1]) $dir | Out-Null
}
Write-Host "已从备份重新解包原始资源"

& $py (Join-Path $tools "makedark.py")  (Join-Path $srcD "Default\appframework\config\theme.xml")
& $py (Join-Path $tools "skinpatch.py") apply (Join-Path $srcD "Default") | Select-Object -Last 1
& $py (Join-Path $tools "skinpatch.py") apply (Join-Path $srcD "Res")     | Select-Object -Last 1
& $py (Join-Path $tools "gmdark.py")    (Join-Path $srcD "Default")       | Select-Object -Last 1
& $py (Join-Path $tools "gmdark.py")    (Join-Path $srcD "Xtml")          | Select-Object -Last 1

New-Item -ItemType Directory -Force -Path $outD | Out-Null
& $py (Join-Path $tools "rdb.py") pack (Join-Path $srcD "Default") (Join-Path $outD "Default.rdb") --manifest (Join-Path $bakD "Default.rdb.orig")
& $py (Join-Path $tools "rdb.py") pack (Join-Path $srcD "Res")     (Join-Path $outD "Res.rdb")     --manifest (Join-Path $bakD "Res.rdb.orig")
& $py (Join-Path $tools "rdb.py") pack (Join-Path $srcD "Xtml")    (Join-Path $outD "Xtml.rdb")    --manifest (Join-Path $bakD "Xtml.rdb.orig")

# -------------------------------------------------------------------- 安装
if ($Install) {
    Stop-Tim
    Copy-Item (Join-Path $outD "Default.rdb") (Join-Path $resDir "Themes\Default.rdb") -Force
    Copy-Item (Join-Path $outD "Res.rdb")     (Join-Path $resDir "Res.rdb")            -Force
    Copy-Item (Join-Path $outD "Xtml.rdb")    (Join-Path $resDir "Xtml.rdb")           -Force
    Write-Host "资源已安装"

    if (-not $SkipDllPatch) {
        # 两处引擎补丁：把代码里写死的黑字强制成白色
        & $py (Join-Path $tools "patch_dll.py") --tim-dir $TimDir --apply
    }

    Clear-TimCache
    if (-not $NoRestart) { Start-Tim }
}
