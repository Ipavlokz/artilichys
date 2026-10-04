$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$target = Join-Path $root 'vendor\unicorn'
$commit = '3be31e8314926bed782a137c95c9003df259639d'
if (!(Test-Path (Join-Path $target 'python-api\Lib\UnicornPy.pyd'))) {
    New-Item -ItemType Directory -Force (Join-Path $root 'vendor') | Out-Null
    $zip = Join-Path $root 'vendor\unicorn-sdk.zip'
    Write-Host 'Descargando SDK desde el repositorio oficial unicorn-bi...'
    Invoke-WebRequest -UseBasicParsing "https://github.com/unicorn-bi/Unicorn-Hybrid-Black-Windows-APIs/archive/$commit.zip" -OutFile $zip
    $stage = Join-Path $root 'vendor\unicorn-extracted'
    Expand-Archive -Path $zip -DestinationPath $stage -Force
    Move-Item (Join-Path $stage "Unicorn-Hybrid-Black-Windows-APIs-$commit") $target
    Remove-Item $stage, $zip -Recurse -Force
}
Write-Host 'SDK oficial preparado. La licencia del fabricante sigue siendo necesaria.'
