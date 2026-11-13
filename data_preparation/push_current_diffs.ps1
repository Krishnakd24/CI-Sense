$ErrorActionPreference = 'Stop'
$repo = 'https://github.com/Krishnakd24/CI-SENSE_DATA_SETS.git'
$source = 'D:\CI_sense_DATA\Final_data\diffs'
$checkout = Join-Path $PSScriptRoot 'ci_sense_diffs_fresh_checkout'
if (-not (Test-Path -LiteralPath $source -PathType Container)) { throw 'Current diffs folder not found.' }
if (Test-Path -LiteralPath $checkout) { throw "Checkout already exists: $checkout. Inspect it before retrying." }
git clone $repo $checkout
if ($LASTEXITCODE -ne 0) { throw 'Clone failed.' }
$destination = Join-Path $checkout 'diffs'
if (Test-Path -LiteralPath $destination) { throw 'The remote already contains a diffs folder; inspect it before replacing anything.' }
Copy-Item -LiteralPath $source -Destination $destination -Recurse
git -C $checkout add -- diffs
if ($LASTEXITCODE -ne 0) { throw 'Git add failed.' }
git -C $checkout commit -m 'Add current test dataset diffs'
if ($LASTEXITCODE -ne 0) { throw 'Commit failed.' }
git -C $checkout push
if ($LASTEXITCODE -ne 0) { throw "Push failed; commit remains in $checkout." }
Write-Host 'Current diffs pushed successfully.'
