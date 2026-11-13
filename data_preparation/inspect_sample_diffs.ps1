$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$info = Import-Csv -LiteralPath (Join-Path $root 'Project_Info.csv')
$projects = @($info | ForEach-Object { $_.'Project '.Trim() } | Where-Object { $_ })
$output = Join-Path $root 'sample_commit_diffs'
New-Item -ItemType Directory -Path $output -Force | Out-Null
$priorSummaries = @{}
$summaryPath = Join-Path $output 'summary.csv'
if (Test-Path -LiteralPath $summaryPath) {
 foreach ($entry in (Import-Csv -LiteralPath $summaryPath)) { $priorSummaries[$entry.project] = $entry }
}
$headers = @{ 'User-Agent' = 'CI-diff-research'; 'Accept' = 'application/vnd.github+json'; 'X-GitHub-Api-Version' = '2022-11-28' }
if ($env:GITHUB_TOKEN) { $headers['Authorization'] = 'Bearer ' + $env:GITHUB_TOKEN }
$summary = foreach ($project in $projects) {
 $remaining = $null
 try {
  $record = @($info | Where-Object { $_.'Project '.Trim() -eq $project })
  if ($record.Count -ne 1) { throw 'Expected exactly one project entry.' }
  $url = $record[0].URL.Trim().TrimEnd('/'); $requested = $record[0].SHA.Trim()
  if ($url -notmatch '^https://github\.com/([^/]+)/([^/]+)$') { throw 'Invalid GitHub URL.' }
  $repo = $Matches[1] + '/' + ($Matches[2] -replace '\.git$','')
  $nonce = [Guid]::NewGuid().ToString('N')
  $commit = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/commits/${requested}?nonce=$nonce" -Headers $headers
  $parents = @($commit.parents | ForEach-Object { $_.sha })
  if ($parents.Count -eq 0) { throw 'Root commit has no parent to compare.' }
  $parent = $parents[0]
  $diffHeaders = $headers.Clone(); $diffHeaders['Accept']='application/vnd.github.v3.diff'
  $diff = Invoke-WebRequest -UseBasicParsing -Uri "https://api.github.com/repos/$repo/compare/$parent...$($commit.sha)?nonce=$nonce" -Headers $diffHeaders
  $diffFile = Join-Path $output ($project + '.diff')
  if ($diff.Content -is [byte[]]) { [IO.File]::WriteAllBytes($diffFile, $diff.Content) }
  else { [IO.File]::WriteAllText($diffFile, [string]$diff.Content, [Text.UTF8Encoding]::new($false)) }
  $fileCount = ([regex]::Matches([Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($diffFile)), '(?m)^diff --git ')).Count
  [pscustomobject]@{project=$project; repository=$url; requested_sha=$requested; commit_sha=$commit.sha; parent_sha=$parent; parent_count=$parents.Count; commit_date=$commit.commit.committer.date; commit_message=$commit.commit.message; changed_files=$fileCount; additions=$commit.stats.additions; deletions=$commit.stats.deletions; diff_file=$diffFile; error=''}
 } catch {
  $reason = $_.Exception.Message
  $response = $_.Exception.Response
  if ($null -ne $response) {
   $remaining = $response.Headers['X-RateLimit-Remaining']
   $reset = $response.Headers['X-RateLimit-Reset']
   if ($remaining) { $reason += "; rate-limit remaining=$remaining" }
   if ($reset) { $reason += "; rate-limit reset UTC=$([DateTimeOffset]::FromUnixTimeSeconds([long]$reset).UtcDateTime.ToString('u'))" }
   try {
    $reader = [IO.StreamReader]::new($response.GetResponseStream())
    try { $body = $reader.ReadToEnd() } finally { $reader.Dispose() }
    if ($body) { $message = ($body | ConvertFrom-Json).message; if ($message) { $reason += "; GitHub: $message" } }
   } catch { }
  }
  [pscustomobject]@{project=$project; repository=''; requested_sha=''; commit_sha=''; parent_sha=''; parent_count=''; commit_date=''; commit_message=''; changed_files=''; additions=''; deletions=''; diff_file=''; error=$reason}
  if ($remaining -eq '0') { Write-Warning 'GitHub API rate limit exhausted. Stopping; rerun after the reset.'; break }
 }
}
$byProject = @{}
foreach ($entry in $summary) { $byProject[$entry.project] = $entry }
$combined = foreach ($project in $projects) {
 $entry = if ($byProject.ContainsKey($project)) { $byProject[$project] } elseif ($priorSummaries.ContainsKey($project)) { $priorSummaries[$project] } else { [pscustomobject]@{project=$project; repository=''; requested_sha=''; commit_sha=''; parent_sha=''; parent_count=''; commit_date=''; commit_message=''; changed_files=''; additions=''; deletions=''; diff_file=''; error='Not attempted'} }
 $description = if ($priorSummaries.ContainsKey($project) -and $priorSummaries[$project].git_diff_summary) { $priorSummaries[$project].git_diff_summary } else { 'NA' }
 $entry | Add-Member -NotePropertyName git_diff_summary -NotePropertyValue $description -Force
 $entry
}
$combined | Export-Csv -LiteralPath $summaryPath -Encoding UTF8 -NoTypeInformation
$summary | Format-Table project,parent_count,changed_files,additions,deletions,error -AutoSize
