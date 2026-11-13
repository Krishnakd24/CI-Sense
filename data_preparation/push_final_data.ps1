$ErrorActionPreference = 'Stop'
$repository = 'https://github.com/Krishnakd24/CI-SENSE_DATA_SETS.git'
$source = 'D:\CI_sense_DATA\Final_data'
$checkout = Join-Path $PSScriptRoot 'ci_sense_datasets_checkout'
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw 'Final_data folder not found.' }
if (Test-Path -LiteralPath $checkout) { throw "Checkout already exists: $checkout. Inspect it before retrying." }
git clone $repository $checkout
if ($LASTEXITCODE -ne 0) { throw 'Git clone failed; no files were pushed.' }
Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $checkout -Recurse -Force
git -C $checkout add --all
if ($LASTEXITCODE -ne 0) { throw 'Git add failed.' }
git -C $checkout diff --cached --quiet
if ($LASTEXITCODE -eq 0) { Write-Host 'No changes to publish.'; exit 0 }
if ($LASTEXITCODE -ne 1) { throw 'Could not check staged changes.' }
git -C $checkout commit -m 'Add CI test datasets and diffs'
if ($LASTEXITCODE -ne 0) { throw 'Commit failed; check Git identity and repository settings.' }
git -C $checkout push
if ($LASTEXITCODE -ne 0) { throw "Push failed; your committed changes remain in $checkout." }
Write-Host 'Push completed.'
