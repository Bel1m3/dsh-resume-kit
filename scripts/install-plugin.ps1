<#
  把本地的简历插件安装进 DSH 的 profile。

  顺序：先建联接 → 用 node 验证解析 → 再改配置（失败即回滚），不会留下半装状态。
  写 package.json 时必须是 UTF-8 无 BOM：DSH 用 JSON.parse 读清单，带 BOM 会进安全模式。
  本脚本自身是 UTF-8 带 BOM —— Windows PowerShell 5.1 否则会把中文当 GBK 读，直接语法报错。

  用法：
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-plugin.ps1
#>
param(
  [string]$ProfileDir = (Join-Path $env:APPDATA 'dsh-desktop\harness\profiles\web'),
  [string]$PluginDir  = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $ProfileDir)) { throw "找不到 profile 目录：$ProfileDir" }
if (-not (Test-Path (Join-Path $PluginDir 'package.json'))) { throw "找不到插件目录：$PluginDir" }

# 包名从 package.json 读，以后改名字不用再动脚本
$PluginName = (Get-Content (Join-Path $PluginDir 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json).name
if (-not $PluginName) { throw '读不到插件 package.json 里的 name' }
Write-Host "插件包名：$PluginName"

$profileJsonPath = Join-Path $ProfileDir 'package.json'
if (-not (Test-Path $profileJsonPath)) { throw "profile 里没有 package.json：$profileJsonPath" }

# ---------- 1) 目录联接 ----------
$nm = Join-Path $ProfileDir 'node_modules'
if (-not (Test-Path $nm)) { New-Item -ItemType Directory -Path $nm | Out-Null }
$linkPath = Join-Path $nm $PluginName

if (Test-Path $linkPath) {
  $item = Get-Item $linkPath -Force
  if ($item.LinkType -eq 'Junction' -or $item.LinkType -eq 'SymbolicLink') {
    Write-Host "已存在联接，重建：$linkPath"
    $item.Delete()
  } else {
    throw "$linkPath 已存在且不是联接，请手动确认后删除"
  }
}
New-Item -ItemType Junction -Path $linkPath -Target $PluginDir | Out-Null
Write-Host "已创建联接：$linkPath -> $PluginDir"

# ---------- 2) 解析验证 ----------
$probe = "console.log(require.resolve('$PluginName/package.json', { paths: [process.argv[1]] }))"
$resolved = & node -e $probe $ProfileDir 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host "解析失败，回滚联接：" -ForegroundColor Red
  (Get-Item $linkPath -Force).Delete()
  throw "profile 无法解析 $PluginName，已回滚，未改动任何配置：$resolved"
}
Write-Host "解析验证通过：$resolved"

# ---------- 3) 写配置（先备份）----------
$stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = "$profileJsonPath.icc-backup-$stamp"
Copy-Item $profileJsonPath $backup
Write-Host "已备份 profile 配置 -> $backup"

$pkg = Get-Content $profileJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json

if (-not $pkg.dependencies) {
  $pkg | Add-Member -NotePropertyName dependencies -NotePropertyValue ([pscustomobject]@{}) -Force
}
$linkTarget = 'link:' + ($PluginDir -replace '\\', '/')
$pkg.dependencies | Add-Member -NotePropertyName $PluginName -NotePropertyValue $linkTarget -Force
Write-Host "dependencies.$PluginName = $linkTarget"

if (-not $pkg.dsh -or -not $pkg.dsh.profile) { throw "profile 的 package.json 里没有 dsh.profile，可能不是标准 profile" }
$bundles = @($pkg.dsh.profile.bundles)
if ($bundles -notcontains $PluginName) {
  $bundles += $PluginName
  $pkg.dsh.profile | Add-Member -NotePropertyName bundles -NotePropertyValue $bundles -Force
  Write-Host "dsh.profile.bundles += $PluginName"
} else {
  Write-Host "dsh.profile.bundles 里已经有 $PluginName"
}

$json = $pkg | ConvertTo-Json -Depth 30
[System.IO.File]::WriteAllText($profileJsonPath, $json, (New-Object System.Text.UTF8Encoding $false))
Write-Host "已写入 $profileJsonPath"

# ---------- 4) 用 DSH 的方式复验 ----------
$verify = & node -e "JSON.parse(require('fs').readFileSync(process.argv[1], 'utf8')); console.log('manifest-ok')" $profileJsonPath 2>&1
if ($LASTEXITCODE -ne 0) {
  Copy-Item $backup $profileJsonPath -Force
  Write-Host "清单校验失败，已还原备份：$backup" -ForegroundColor Red
  throw "写入后的 package.json 无法被 JSON.parse 解析，已回滚"
}
Write-Host "清单校验通过（UTF-8 无 BOM）"

Write-Host ''
Write-Host '安装完成。重启 DSH Desktop 生效。' -ForegroundColor Green
Write-Host '回滚：powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\uninstall-plugin.ps1'
