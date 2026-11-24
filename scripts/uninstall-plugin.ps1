<#
  卸载本插件：删目录联接、dependencies 条目、bundles 条目。
  包名从插件目录的 package.json 读，卸载时不用手写。
#>
param(
  [string]$ProfileDir = (Join-Path $env:APPDATA 'dsh-desktop\harness\profiles\web'),
  [string]$PluginDir  = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$pkgJson = Join-Path $PluginDir 'package.json'
$PluginName = if (Test-Path $pkgJson) {
  (Get-Content $pkgJson -Raw -Encoding UTF8 | ConvertFrom-Json).name
} else { 'dsh-resume-kit' }
if (-not $PluginName) { throw '读不到插件 package.json 里的 name' }
Write-Host "插件包名：$PluginName"

$profileJsonPath = Join-Path $ProfileDir 'package.json'
if (-not (Test-Path $profileJsonPath)) { throw "找不到 $profileJsonPath" }

$stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
Copy-Item $profileJsonPath "$profileJsonPath.icc-backup-$stamp"
Write-Host "已备份 profile 配置 -> $profileJsonPath.icc-backup-$stamp"

$pkg = Get-Content $profileJsonPath -Raw -Encoding UTF8 | ConvertFrom-Json

if ($pkg.dependencies -and $pkg.dependencies.PSObject.Properties.Name -contains $PluginName) {
  $pkg.dependencies.PSObject.Properties.Remove($PluginName)
  Write-Host "已移除 dependencies.$PluginName"
}

if ($pkg.dsh -and $pkg.dsh.profile -and $pkg.dsh.profile.bundles) {
  $kept = @($pkg.dsh.profile.bundles) | Where-Object { $_ -ne $PluginName }
  $pkg.dsh.profile | Add-Member -NotePropertyName bundles -NotePropertyValue $kept -Force
  Write-Host "已从 bundles 里移除 $PluginName"
}

$json = $pkg | ConvertTo-Json -Depth 30
[System.IO.File]::WriteAllText($profileJsonPath, $json, (New-Object System.Text.UTF8Encoding $false))

$verify = & node -e "JSON.parse(require('fs').readFileSync(process.argv[1], 'utf8')); console.log('manifest-ok')" $profileJsonPath 2>&1
if ($LASTEXITCODE -ne 0) {
  Copy-Item "$profileJsonPath.icc-backup-$stamp" $profileJsonPath -Force
  Write-Host "清单校验失败，已还原备份" -ForegroundColor Red
  throw "package.json 无法被 JSON.parse 解析，已回滚"
}
Write-Host "清单校验通过（UTF-8 无 BOM）"

$linkPath = Join-Path (Join-Path $ProfileDir 'node_modules') $PluginName
if (Test-Path $linkPath) {
  $item = Get-Item $linkPath -Force
  if ($item.LinkType -eq 'Junction' -or $item.LinkType -eq 'SymbolicLink') {
    $item.Delete()
    Write-Host "已删除联接：$linkPath"
  } else {
    Write-Host "$linkPath 不是联接，未删除，请手动确认。" -ForegroundColor Yellow
  }
}

Write-Host '卸载完成，重启 DSH 生效。' -ForegroundColor Green
