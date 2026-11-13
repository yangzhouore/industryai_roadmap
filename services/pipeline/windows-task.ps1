[CmdletBinding()]
param(
    [string]$OutputPath,
    [string]$PythonExecutable,
    [string]$TaskName = 'Industrial AI Daily (disabled dry-run)',
    [switch]$Register
)
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (-not $OutputPath) { $OutputPath = Join-Path $workspace 'artifacts/mvp4/windows-task.xml' }
$resolvedOutput = [IO.Path]::GetFullPath($OutputPath)
if (-not $resolvedOutput.StartsWith($workspace + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Export must stay inside this workspace.'
}
if (-not $PythonExecutable) { $PythonExecutable = (Get-Command python -ErrorAction Stop).Source }
$PythonExecutable = (Resolve-Path -LiteralPath $PythonExecutable).Path
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$start = (Get-Date).Date.ToString('yyyy-MM-ddTHH:mm:ss')
function Escape-Xml([string]$Value) { [Security.SecurityElement]::Escape($Value) }
$command = Escape-Xml $PythonExecutable
$workingDirectory = Escape-Xml $workspace
$description = Escape-Xml 'Disabled dry-run template. Tick checks 07:00 Europe/Berlin; no API permission is granted.'
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>$description</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <Repetition><Interval>PT15M</Interval><Duration>P1D</Duration><StopAtDurationEnd>false</StopAtDurationEnd></Repetition>
      <StartBoundary>$start</StartBoundary><Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
    <BootTrigger><Enabled>true</Enabled><Delay>PT2M</Delay></BootTrigger>
    <LogonTrigger><Enabled>true</Enabled><UserId>$identity</UserId></LogonTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>$identity</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable><WakeToRun>true</WakeToRun>
    <Enabled>false</Enabled><ExecutionTimeLimit>PT20M</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author"><Exec><Command>$command</Command><Arguments>-m services.pipeline.daily tick --dry-run --resume --report artifacts/daily-status.json</Arguments><WorkingDirectory>$workingDirectory</WorkingDirectory></Exec></Actions>
</Task>
"@
[xml]$parsed = $xml
$namespace = New-Object Xml.XmlNamespaceManager($parsed.NameTable)
$namespace.AddNamespace('t', 'http://schemas.microsoft.com/windows/2004/02/mit/task')
if ($parsed.SelectSingleNode('/t:Task/t:Settings/t:Enabled', $namespace).InnerText -ne 'false') { throw 'Task must remain disabled.' }
if ($parsed.SelectSingleNode('/t:Task/t:Actions/t:Exec/t:Arguments', $namespace).InnerText -match 'allow-paid') { throw 'No paid execution is permitted in this template.' }
New-Item -ItemType Directory -Path (Split-Path -Parent $resolvedOutput) -Force | Out-Null
[IO.File]::WriteAllText($resolvedOutput, $xml, [Text.Encoding]::Unicode)
Write-Output "Exported disabled dry-run task: $resolvedOutput"
if ($Register) {
    Register-ScheduledTask -TaskName $TaskName -Xml $xml -ErrorAction Stop | Select-Object TaskName, State
    Write-Output 'Registered disabled only. No task has been enabled and no paid permission granted.'
}
