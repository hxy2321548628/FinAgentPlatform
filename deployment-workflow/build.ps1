param([switch]$WithImages, [switch]$RunChecks, [string]$Ref = 'origin/main')
$ErrorActionPreference = 'Stop'
$packArgs = @((Join-Path $PSScriptRoot 'package.py'), '--ref', $Ref)
if ($WithImages) { $packArgs += '--with-images' }
if ($RunChecks) { $packArgs += '--run-checks' }
& python @packArgs
if ($LASTEXITCODE -ne 0) { throw '打包或门禁失败' }
