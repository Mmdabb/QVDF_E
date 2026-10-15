param(
  [string]$WorkbookPath = (Join-Path $PSScriptRoot '..\Sensor78_Emission_Comparison_Simple.xlsx'),
  [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\..\..\output\sensor78\workbook')
)
$ErrorActionPreference = 'Stop'
$sourcePath = (Resolve-Path -LiteralPath $WorkbookPath).Path
$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
$bookPath = Join-Path $outputPath 'Sensor78_Emission_Comparison_Excel_Validated.xlsx'
$reportPath = Join-Path $outputPath 'native_excel_validation.json'
if ($sourcePath -eq $bookPath -or $sourcePath -eq $reportPath) { throw 'Output collides with the source workbook.' }
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
$workingRoot = Join-Path $repositoryRoot 'debug\output'
foreach ($destination in @($bookPath,$reportPath)) {
  $insideRepository=$destination.StartsWith($repositoryRoot + [System.IO.Path]::DirectorySeparatorChar,[System.StringComparison]::OrdinalIgnoreCase)
  $insideWorking=$destination.StartsWith($workingRoot + [System.IO.Path]::DirectorySeparatorChar,[System.StringComparison]::OrdinalIgnoreCase)
  if ($insideRepository -and -not $insideWorking) {
    throw 'Repository source/reference folders are read-only. Choose debug/output/ or an external working output directory.'
  }
}
# Reject reparse-point ancestors rather than risk a junction redirecting output
# into a protected reference folder on Windows PowerShell 5.1.
$ancestor = $outputPath
while ($ancestor) {
  if (Test-Path -LiteralPath $ancestor) {
    $item = Get-Item -LiteralPath $ancestor -Force
    if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
      throw 'Output directories with reparse-point ancestors are not supported; choose a direct local working directory.'
    }
  }
  $ancestor = [System.IO.Path]::GetDirectoryName($ancestor)
}
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
if ((Test-Path -LiteralPath $bookPath) -or (Test-Path -LiteralPath $reportPath)) {
  throw 'Validation output files already exist. Choose a fresh output directory to avoid overwriting earlier evidence.'
}
Copy-Item -LiteralPath $sourcePath -Destination $bookPath -Force
$excel = $null
$book = $null
$report = [ordered]@{ engine='Microsoft Excel, separate hidden instance'; path=[System.IO.Path]::GetFileName($bookPath); baseline=$null; sensitivities=@(); error_cells=@(); links=@(); connections=$null; restored=$false; saved_reopened=$false; passed=$false; failures=@() }
function Snapshot($workbook) {
  $s=$workbook.Worksheets.Item('08 Results')
  $v=$s.Range('B7:I11').Value2
  $rows=@()
  for($i=1;$i -le 5;$i++){
    $row=@()
    for($j=1;$j -le 8;$j++){
      $value=$v[$i,$j]
      if($null -eq $value -or $value -is [string] -or $value -is [bool]) { throw 'Results contain a missing or nonnumeric value.' }
      $number=[double]$value
      if([double]::IsNaN($number) -or [double]::IsInfinity($number)) { throw 'Results contain a non-finite value.' }
      $row+= $number
    }
    $rows+=,@($row)
  }
  return ,$rows
}
function MaximumDifference($left,$right) {
  $difference=0.0
  for($i=0;$i -lt 5;$i++){ for($j=0;$j -lt 8;$j++){ $difference=[Math]::Max($difference,[Math]::Abs([double]$left[$i][$j]-[double]$right[$i][$j])) } }
  return $difference
}
try {
  $excel=New-Object -ComObject Excel.Application
  $excel.Visible=$false
  $excel.DisplayAlerts=$false
  $excel.EnableEvents=$false
  $excel.ScreenUpdating=$false
  $excel.AutomationSecurity=3
  $book=$excel.Workbooks.Open($bookPath,0,$false)
  $excel.Calculation=-4135
  $excel.CalculateFullRebuild()
  $base=Snapshot $book
  $report.baseline=$base
  foreach($case in @(
    @{name='count_multiplier_plus_1pct';sheet='01 Traffic inputs';cell='B20';factor=1.01},
    @{name='one_recorded_speed_minus_10pct';sheet='01 Traffic inputs';cell='C40';factor=0.9},
    @{name='theta_plus_1pct';sheet='01 Traffic inputs';cell='B16';factor=1.01},
    @{name='low_speed_CO2_rate_plus_1pct';sheet='02 Emission rates';cell='D7';factor=1.01}
  )) {
    $cell=$book.Worksheets.Item($case.sheet).Range($case.cell)
    $old=$cell.Value2
    $cell.Value2=[double]$old*[double]$case.factor
    $excel.CalculateFull()
    $changed=Snapshot $book
    $report.sensitivities+=@{name=$case.name; results=$changed; original=$old; revised=[double]$old*[double]$case.factor}
    $cell.Value2=$old
    $excel.CalculateFull()
  }
  $restored=Snapshot $book
  $maxDifference=MaximumDifference $base $restored
  $report.restored=($maxDifference -lt 1E-8)
  $report.restore_max_difference=$maxDifference
  foreach($s in $book.Worksheets){
    try { $errs=$s.UsedRange.SpecialCells(-4123,16); if($null -ne $errs){$report.error_cells+=@{sheet=$s.Name;range=$errs.Address()}} } catch {}
  }
  foreach($linkType in @(1,2)) { $links=$book.LinkSources($linkType); if($null -ne $links){$report.links+=@($links)} }
  $report.connections=$book.Connections.Count
  $excel.Calculation=-4105
  $book.Save()
  $book.Close($false)
  $book=$null
  $book=$excel.Workbooks.Open($bookPath,0,$true)
  $again=Snapshot $book
  $report.reopened=$again
  $report.reopen_max_difference=MaximumDifference $base $again
  $report.saved_reopened=($report.reopen_max_difference -lt 1E-8)
  $report.validity=$book.Worksheets.Item('05 Reconstructed R').Range('B20').Value2
  if(-not $report.restored){$report.failures+='Restored results differ from the baseline.'}
  if(-not $report.saved_reopened){$report.failures+='Saved/reopened results differ from the baseline.'}
  if($report.error_cells.Count -gt 0){$report.failures+='Formula error cells were found.'}
  if($report.links.Count -gt 0 -or $report.connections -ne 0){$report.failures+='External data dependencies were found.'}
  if($report.validity -ne 'VALID'){$report.failures+='The fitted traffic model is not VALID.'}
  $report.passed=($report.failures.Count -eq 0)
  $book.Close($false)
  $book=$null
} catch {
  $report.failures+=$_.Exception.Message
  $report.passed=$false
} finally {
  if($null -ne $book){$book.Close($false)}
  if($null -ne $excel){$excel.Quit();[void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)}
  [GC]::Collect();[GC]::WaitForPendingFinalizers()
  $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportPath -Encoding UTF8
}
Write-Output ($report | ConvertTo-Json -Depth 12)
if(-not $report.passed){throw ('Native Excel validation failed: ' + ($report.failures -join ' '))}
