# Nightly sleep: stop llama-server (+ anything lc started), suspend (S3, not hibernate), restart lc idle watcher on wake.
# Usage: nightly-sleep.ps1 [-DryRun]   Log: $env:TEMP\nightly-sleep.log
param([switch]$DryRun)
$log = Join-Path $env:TEMP 'nightly-sleep.log'
function Log($m) { Add-Content -Path $log -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}{2}" -f (Get-Date), $(if ($DryRun) { '[DRYRUN] ' } else { '' }), $m) }
$lc = 'C:\Users\DaGuest\local-coder\bin\lc.cmd'
Log 'start'
$procs = @(Get-Process -Name 'llama-server' -ErrorAction SilentlyContinue)
Log ("llama-server processes: {0} (pids: {1})" -f $procs.Count, (($procs | ForEach-Object Id) -join ','))
if ($DryRun) { Log "would run: $lc stop" } else { try { & $lc stop *>&1 | ForEach-Object { Log "lc stop: $_" } } catch { Log "lc stop failed: $_" } }
foreach ($p in $procs) {
  if ($DryRun) { Log "would stop llama-server pid $($p.Id)" }
  else { try { Stop-Process -Id $p.Id -Force -ErrorAction Stop; Log "stopped pid $($p.Id)" } catch { Log "stop pid $($p.Id) failed: $_" } }
}
if ($DryRun) { Log 'would wait 10 s, then SetSuspendState(Suspend), then run: lc watch start'; Log 'done'; exit 0 }
Start-Sleep -Seconds 10
Log 'suspending'
Add-Type -AssemblyName System.Windows.Forms
[void][System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)
Log 'resumed from sleep'
try { & $lc watch start *>&1 | ForEach-Object { Log "lc watch start: $_" } } catch { Log "watch start failed: $_" }
Log 'done'
