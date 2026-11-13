$ErrorActionPreference='Stop'
$base=$PSScriptRoot
$inputRows=@(Import-Csv (Join-Path $base 'extracted_test_code_V1.csv'))
$comparisons=@(Import-Csv (Join-Path $base 'xml_test_name_comparison.csv'))
$byFile=@{}
foreach($c in $comparisons){ if(-not $byFile.ContainsKey($c.xml_file_name)){$byFile[$c.xml_file_name]=[System.Collections.Generic.List[object]]::new()}; $byFile[$c.xml_file_name].Add($c) }
$results=[System.Collections.Generic.List[object]]::new()
function Attr($element,$name){ if($null -ne $element -and $element.HasAttribute($name)){return $element.GetAttribute($name)}; return '' }
function ChildText($element,$name){ $nodes=@($element.SelectNodes("./*[local-name()='$name']")); return (($nodes | ForEach-Object { $_.InnerText }) -join "`n") }
function Collect($suites,$output) {
 foreach($suite in $suites){
  foreach($case in $suite.SelectNodes("./*[local-name()='testcase']")){ $output.Add([pscustomobject]@{ case=$case; suite=$suite }) }
  Collect @($suite.SelectNodes("./*[local-name()='testsuite']")) $output
 }
}
foreach($row in $inputRows){
 $original=$row.test_name; $filename=$original+'.xml'; $path=Join-Path (Join-Path $base $row.Project_name) $filename
 $matches=@(); $status=''; $doc=$null
 if(-not (Test-Path -LiteralPath $path)){ $status='XML_NOT_FOUND' }
 else { try {
   $doc=[System.Xml.XmlDocument]::new(); $doc.XmlResolver=$null; $doc.Load($path)
   $all=[System.Collections.Generic.List[object]]::new()
   if($doc.DocumentElement.LocalName -eq 'testsuite'){ Collect @($doc.DocumentElement) $all } else { Collect @($doc.DocumentElement.SelectNodes("./*[local-name()='testsuite']")) $all }
   $matches=@($all | Where-Object { ((Attr $_.case 'classname')+'#'+(Attr $_.case 'name')) -ceq $original })
   if($matches.Count -eq 0 -and $byFile.ContainsKey($filename)){
     $corrected=@($byFile[$filename] | Where-Object { $_.same -eq 'false' -and $_.corrected_test_name } | Select-Object -ExpandProperty corrected_test_name -Unique)
     if($corrected.Count -eq 1){ $target=$corrected[0]; $matches=@($all | Where-Object { ((Attr $_.case 'classname')+'#'+(Attr $_.case 'name')) -ceq $target -and $null -ne $_.case.SelectSingleNode("./*[local-name()='failure' or local-name()='error']") }) }
   }
   if($matches.Count -eq 0){$status='TESTCASE_NOT_FOUND'} elseif($matches.Count -gt 1){$status='MULTIPLE_MATCHES'} else {$status='MATCHED'}
 } catch { $status='XML_PARSE_ERROR'; $doc=$null } }
 if($matches.Count -eq 0){$matches=@($null)}
 foreach($match in $matches){
  $case=if($null -ne $match){$match.case}else{$null}; $suite=if($null -ne $match){$match.suite}else{$null}
  $result=''; $failure=''; $errorMessage=''; $exception=''; $stack=''; $expected=''; $actual=''; $source=''; $line=''; $out=''; $err=''; $duration=''; $class=''; $name=''; $testid=''; $attrs=''; $suiteName=''; $suiteId=''; $suitePackage=''; $suiteTimestamp=''; $suiteHost=''
  if($null -ne $case){
   $class=Attr $case 'classname'; $name=Attr $case 'name'; $testid=$class+'#'+$name; $duration=Attr $case 'time'; $out=ChildText $case 'system-out'; $err=ChildText $case 'system-err'
   $failureNodes=@($case.SelectNodes("./*[local-name()='failure']")); $errorNodes=@($case.SelectNodes("./*[local-name()='error']")); $skipped=@($case.SelectNodes("./*[local-name()='skipped']"))
   if($errorNodes.Count){$result='ERROR'} elseif($failureNodes.Count){$result='FAIL'} elseif($skipped.Count){$result='SKIPPED'} else {$result='PASS'}
   $failure=(@($failureNodes | ForEach-Object { Attr $_ 'message' }) | Where-Object {$_}) -join "`n"
   $errorMessage=(@($errorNodes | ForEach-Object { Attr $_ 'message' }) | Where-Object {$_}) -join "`n"
   $problems=@($failureNodes)+@($errorNodes)
   $exception=(@($problems | ForEach-Object { Attr $_ 'type' } | Where-Object {$_} | Select-Object -Unique)) -join '; '
   $stack=(@($problems | ForEach-Object {$_.InnerText} | Where-Object {$_})) -join "`n--- additional failure ---`n"
   if(-not $exception -and $stack -match '(?m)^\s*([\w.$]+(?:Exception|Error|Failure))(?::|\s|$)'){$exception=$Matches[1]}
   if($stack -match '\(([\w.$-]+\.(?:java|kt|scala|groovy)):(\d+)\)'){$source=$Matches[1];$line=$Matches[2]}
   $assertText=$failure+"`n"+$errorMessage+"`n"+$stack
   if($assertText -match '(?is)expected\s*:\s*<([^\r\n]*?)>\s*but\s*(?:was|actual)\s*:\s*<([^\r\n]*?)>'){$expected=$Matches[1];$actual=$Matches[2]}
   elseif($assertText -match '(?is)expected\s*<([^\r\n]*?)>\s*but\s*was\s*<([^\r\n]*?)>'){$expected=$Matches[1];$actual=$Matches[2]}
   $suiteName=Attr $suite 'name';$suiteId=Attr $suite 'id';$suitePackage=Attr $suite 'package';$suiteTimestamp=Attr $suite 'timestamp';$suiteHost=Attr $suite 'hostname'
   $map=[ordered]@{}; foreach($a in $doc.DocumentElement.Attributes){$map[$a.Name]=$a.Value}; $attrs=ConvertTo-Json -InputObject $map -Compress
  }
  $results.Add([pscustomobject]@{project=$row.Project_name; input_test_identifier=$original; input_row_id=$row.id; test_name=$name; test_class=$class; test_identifier=$testid; execution_result=$result; exception_type=$exception; failure_message=$failure; error_message=$errorMessage; stack_trace=$stack; source_file=$source; line_number=$line; expected_value=$expected; actual_value=$actual; duration_seconds=$duration; test_stdout=$out; test_stderr=$err; xml_filename=$filename; suite_name=$suiteName; suite_id=$suiteId; suite_package=$suitePackage; suite_timestamp=$suiteTimestamp; suite_hostname=$suiteHost; report_attributes_json=$attrs; match_status=$status })
 }
}
foreach ($result in $results) {
 foreach ($property in $result.PSObject.Properties) {
  if ($null -eq $property.Value -or $property.Value -ceq '') { $property.Value = 'NA' }
 }
}
$results | Export-Csv -LiteralPath (Join-Path $base 'test_failure_details.csv') -NoTypeInformation -Encoding UTF8
"Input rows: $($inputRows.Count); output rows: $($results.Count)"
$results | Group-Object match_status | Select-Object Name,Count
$results | Group-Object execution_result | Select-Object Name,Count
