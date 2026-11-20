# Runs one chunk of the experiment. Rerun the same command to continue where it stopped.
#
#   tools\run.ps1 study -MaxHours 8            # the study; first stops at the early gate (below)
#   tools\run.ps1 study -MaxEpisodes 50        # or a fixed number of episodes
#   tools\run.ps1 status                       # progress (and the early gate verdict)
#   tools\run.ps1 study -PastGate              # gate failed: continue from the checkpoint anyway
#   tools\run.ps1 study -RestartLibrary        # gate failed, library fixed: redo E/E-minus/E-text
#                                              #   practice from scratch, keeping C's and D's games
#   tools\run.ps1 study -RestartE              # redo only E's practice (and its gate, evaluations, snapshots,
#                                              #   E-text), keeping C, D and E-minus (refused if E-minus's probe fails)
#   tools\speed-test.ps1                       # throughput sweep over server slot counts
#   tools\run.ps1 plots                        # figures + report.html (study so far)
#   tools\serve-model.ps1                      # optional: one shared server for parallel jobs
#
# Early gate (replaces the pilot, amended 2026-11-17): library practice stops after -GateAt games
# (default 75), then E's rules play 30 development games against C. The report is written to
# <run>\gate.json; the study stops unless E wins - C wins >= -GateMargin (default 0).
#
# Stop early at any time: Ctrl-C, or create the file STOP in the run folder
# (\\wsl$\Ubuntu-24.04\root\ll-runs\<phase>\STOP); finished episodes are always kept.
param(
    [Parameter(Position = 0, Mandatory)][ValidateSet('study', 'status', 'bakeoff', 'plots')]
    [string]$Command,
    [Parameter(Position = 1)][string]$Phase = 'study',
    [int]$Workers = 16,               # parallel episodes (memoryless streams run many at once)
    [int]$Slots = 24,                 # server slots if this command starts the server (measured best for the 9B)
    [int]$MaxEpisodes = 0,
    [double]$MaxHours = 0,
    [int]$GateAt = 75,                # early gate after this many library practice games (0 = none)
    [int]$GateMargin = 0,             # gate passes when E wins - C wins >= this
    [switch]$PastGate,
    [switch]$RestartLibrary,
    [switch]$RestartE,                # redo only E (and E-text), keeping C, D and E-minus if its probe passes
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
    if ($LASTEXITCODE -eq 3) {
        Write-Host 'stopped at the early gate (see the message above): rerun with -PastGate to continue, or fix the library and rerun with -RestartLibrary'
        return
    }
    if ($LASTEXITCODE -ne 0) { throw "linux command failed ($LASTEXITCODE)" }
}

if ($Command -eq 'status') {
    Invoke-Linux "$py -m living_library status --output $runs/$Phase"
    return
}
if ($Command -eq 'plots') {
    # Figures + report.html from whatever has run so far, no GPU needed.
    Invoke-Linux "$py tools/plots.py $runs/$Phase --out $runs/figures"
    Write-Host "open \\wsl$\Ubuntu-24.04\root\ll-runs\figures\report.html"
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
        'bakeoff' { $cliArgs = "pilot --config configs/bakeoff-$Model.json --manifest $runs/manifest.json --output $runs/bakeoff-$Model" }
        'study' {
            $cliArgs = "study --manifest $runs/manifest.json --output $runs/study --gate-at $GateAt --gate-margin $GateMargin"
            if ($PastGate) { $cliArgs += ' --past-gate' }
            if ($RestartLibrary) { $cliArgs += ' --restart-library' }
            if ($RestartE) { $cliArgs += ' --restart-streams E' }
        }
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
