# Runs one chunk of the experiment. Rerun the same command to continue where it stopped.
#
#   tools\run.ps1 pilot -MaxHours 3            # run the pilot for up to 3 hours
#   tools\run.ps1 pilot -MaxEpisodes 50        # or a fixed number of episodes
#   tools\run.ps1 status pilot                 # progress
#   tools\run.ps1 study -MaxHours 8            # after freezing (tools\run.ps1 freeze)
#   tools\run.ps1 prepractice -Workers 16      # study practice (D, E) alongside the pilot
#   tools\speed-test.ps1                       # throughput sweep over server slot counts
#   tools\run.ps1 plots                        # figures + report.html (pilot and study so far)
#   tools\serve-model.ps1                      # optional: one shared server for parallel jobs
#
# Stop early at any time: Ctrl-C, or create the file STOP in the run folder
# (\\wsl$\Ubuntu-24.04\root\ll-runs\<phase>\STOP); finished episodes are always kept.
param(
    [Parameter(Position = 0, Mandatory)][ValidateSet('pilot', 'study', 'freeze', 'status', 'bakeoff', 'prepractice', 'plots')]
    [string]$Command,
    [Parameter(Position = 1)][string]$Phase = 'pilot',
    [int]$Workers = 16,               # parallel episodes (memoryless streams run many at once)
    [int]$Slots = 24,                 # server slots if this command starts the server (measured best for the 9B)
    [int]$MaxEpisodes = 0,
    [double]$MaxHours = 0,
    [string]$Model = 'qwen3.5-9b',      # default since 2026-11-15 (see tools/serve-model.ps1)
    [switch]$KeepServer
)
$ErrorActionPreference = 'Stop'
$repo = '/mnt/c/Git Repos/living-library-experiment'
$runs = '/root/ll-runs'
$py = '/root/venvs/living/bin/python'
$distro = 'Ubuntu-24.04'

function Invoke-Linux([string]$cmd) {
    wsl.exe -d $distro -u root --cd $repo -- bash -lc $cmd
    if ($LASTEXITCODE -ne 0) { throw "linux command failed ($LASTEXITCODE)" }
}

if ($Command -eq 'status') {
    Invoke-Linux "$py -m living_library status --output $runs/$Phase"
    return
}
if ($Command -eq 'plots') {
    # Figures + report.html from whatever has run so far (pilot and study), no GPU needed.
    Invoke-Linux "$py tools/plots.py $(if ($Phase -eq 'pilot') { "$runs/pilot $runs/study" } else { "$runs/$Phase" }) --out $runs/figures"
    Write-Host "open \\wsl$\Ubuntu-24.04\root\ll-runs\figures\report.html"
    return
}
if ($Command -eq 'freeze') {
    Invoke-Linux "$py -m living_library freeze --manifest $runs/manifest.json --pilot-dir $runs/pilot --output $runs/frozen.json && cp $runs/frozen.json configs/frozen.json"
    Write-Host 'freeze written to configs\frozen.json - commit it before running the study'
    return
}

# --- the GPU must be free, and the PC must stay awake --------------------------------
if (Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue) {
    throw 'the lc local coder (port 8088) is running and holds the GPU; stop it first with: lc stop'
}
$lc = "$env:USERPROFILE\local-coder\bin\lc.cmd"
if (Test-Path $lc) {
    # The lc idle watcher can sleep the PC when there is no input for 30 min, even mid-run.
    & $lc watch stop 2>$null | Out-Null
}
Add-Type -Namespace Win32 -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(int f);'
[Win32.Power]::SetThreadExecutionState([int]-2147483647) | Out-Null   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED

$server = $null
try {
    if (-not (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue)) {
        Write-Host "starting model server ($Model)..."
        $server = Start-Process powershell -WindowStyle Minimized -PassThru -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSScriptRoot\serve-model.ps1`"",
            '-Model', $Model, '-Slots', $Slots)
        $deadline = (Get-Date).AddMinutes(4)
        while ($true) {
            try { if ((Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 2).status -eq 'ok') { break } } catch {}
            if ($server.HasExited) { throw 'model server exited during startup' }
            if ((Get-Date) -gt $deadline) { throw 'model server did not become ready' }
            Start-Sleep 2
        }
    }
    $budget = ''
    if ($MaxEpisodes -gt 0) { $budget += " --max-episodes $MaxEpisodes" }
    if ($MaxHours -gt 0) { $budget += " --max-hours $MaxHours" }
    $entry = '-m living_library'
    switch ($Command) {
        'pilot' { $cliArgs = "pilot --manifest $runs/manifest.json --output $runs/pilot" }
        'prepractice' { $entry = 'tools/prepractice.py'; $cliArgs = "--manifest $runs/manifest.json --output $runs/study" }
        'bakeoff' { $cliArgs = "pilot --config configs/bakeoff-$Model.json --manifest $runs/manifest.json --output $runs/bakeoff-$Model" }
        'study' { $cliArgs = "study --manifest $runs/manifest.json --freeze $runs/frozen.json --output $runs/study --reuse-pilot $runs/pilot" }
    }
    $log = "$runs/$(if ($Command -eq 'bakeoff') { "bakeoff-$Model" } else { $Command }).log"
    Invoke-Linux "mkdir -p $runs && PYTHONUNBUFFERED=1 $py $entry $cliArgs --workers $Workers$budget 2>&1 | tee -a $log; exit \`${PIPESTATUS[0]}"
}
finally {
    [Win32.Power]::SetThreadExecutionState([int]-2147483648) | Out-Null   # release keep-awake
    if ($server -and -not $KeepServer) {
        Write-Host 'stopping model server'
        Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
    }
}
