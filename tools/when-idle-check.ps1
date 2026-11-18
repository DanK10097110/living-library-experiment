# Waits until the GPU is idle, then: starts the 9B server, runs a short live practice for E
# (tools/mini_practice.py) and the 30-game usefulness check of its manual (tools/manual_check.py),
# stops the server. Keeps Windows awake meanwhile (the lc idle watcher sees the GPU busy and won't sleep).
# Report: \\wsl$\Ubuntu-24.04\root\ll-runs\mini-macla\report.txt
param([int]$Games = 48, [int]$MaxWaitHours = 12)
$ErrorActionPreference = 'Stop'
$repo = 'C:\Git Repos\living-library-experiment'
$log = "$env:TEMP\when-idle-check.log"
function Log($m) { "$(Get-Date -Format 'HH:mm:ss') $m" | Tee-Object -FilePath $log -Append }

# 1. Wait for an idle GPU: < 10% load and < 2 GB used, three checks in a row, no model servers.
$deadline = (Get-Date).AddHours($MaxWaitHours); $quiet = 0
Log 'waiting for the GPU to be idle'
while ($quiet -lt 3) {
    if ((Get-Date) -gt $deadline) { Log 'gave up waiting'; exit 1 }
    $q = (nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits).Split(',') | ForEach-Object { [int]$_.Trim() }
    $busyPort = (Get-NetTCPConnection -LocalPort 8000, 8088 -State Listen -ErrorAction SilentlyContinue)
    if ($q[0] -lt 10 -and $q[1] -lt 2000 -and -not $busyPort) { $quiet++ } else { $quiet = 0 }
    Start-Sleep 60
}
Log 'GPU idle: starting'

# 2. Keep awake (Windows' own sleep timer only counts keyboard/mouse input).
Add-Type -Namespace Win32 -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(int f);'
[Win32.Power]::SetThreadExecutionState([int]-2147483647) | Out-Null
try {
    Start-Process powershell -WindowStyle Hidden -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$repo\tools\serve-model.ps1`"")
    $ready = (Get-Date).AddMinutes(4)
    do { Start-Sleep 3; try { $ok = (Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 2).status -eq 'ok' } catch { $ok = $false } } until ($ok -or (Get-Date) -gt $ready)
    if (-not $ok) { throw 'model server did not start' }
    Log 'server up; running practice and check'
    $cmd = "cd '/mnt/c/Git Repos/living-library-experiment' && rm -rf /root/ll-runs/mini-macla /root/ll-runs/manual-check && " +
           "PYTHONUNBUFFERED=1 /root/venvs/living/bin/python tools/mini_practice.py --games $Games --output /root/ll-runs/mini-macla 2>&1 | grep -v 'Loading weights' > /root/ll-runs/mini-macla-report.txt; " +
           "echo; echo '=== 30-game check (manual vs C) ===' >> /root/ll-runs/mini-macla-report.txt; " +
           "PYTHONUNBUFFERED=1 /root/venvs/living/bin/python tools/manual_check.py /root/ll-runs/mini-macla/rules-full.json /root/ll-runs/old-pilot-9b-v1 --games 30 2>&1 | grep -v 'Loading weights' | tail -5 >> /root/ll-runs/mini-macla-report.txt; " +
           "cp /root/ll-runs/mini-macla-report.txt /root/ll-runs/mini-macla/report.txt"
    wsl.exe -d Ubuntu-24.04 -u root -- bash -lc $cmd
    Log "done (exit $LASTEXITCODE)"
}
finally {
    Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
    [Win32.Power]::SetThreadExecutionState([int]-2147483648) | Out-Null
    Log 'server stopped, keep-awake released'
}
