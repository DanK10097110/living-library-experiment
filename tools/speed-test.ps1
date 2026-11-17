# Sweeps server slot counts (and, for the MoE, the expert-streaming threshold) and measures
# throughput with actor-shaped requests (tools/speed_test.py). About 1-3 min per setting.
# Touches no experiment data. Stop any running experiment first (it shares the GPU).
# Results so far: /root/ll-runs/speed-test.csv (MoE 2026-11-14/15, Qwen3.5-9B 2026-11-15).
#
#   tools\speed-test.ps1                              # 9B: slots 16,24,32
#   tools\speed-test.ps1 -Model qwen3.6-35b-a3b -Slots 8,16,24,32
#   tools\speed-test.ps1 -Slots 16,32 -StreamMinBatch 8,16
param(
    [int[]]$Slots = @(16, 24, 32),
    [int[]]$StreamMinBatch = @(8),
    [int]$ContextPerSlot = 4096,
    [string]$Model = 'qwen3.5-9b'
)
$ErrorActionPreference = 'Stop'
$repo = '/mnt/c/Git Repos/living-library-experiment'
$csv = '/root/ll-runs/speed-test.csv'
if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
    throw 'a model server is already running on port 8000; stop the experiment/server first'
}
foreach ($t in $StreamMinBatch) {
    foreach ($s in $Slots) {
        Write-Host "== slots $s, streaming threshold $t =="
        $srv = Start-Process powershell -WindowStyle Minimized -PassThru -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSScriptRoot\serve-model.ps1`"",
            '-Model', $Model, '-Slots', $s, '-StreamMinBatch', $t, '-ContextPerSlot', $ContextPerSlot)
        try {
            $deadline = (Get-Date).AddMinutes(4)
            do {
                Start-Sleep 2
                if ($srv.HasExited) { throw "server exited (slots $s)" }
                if ((Get-Date) -gt $deadline) { throw 'server did not become ready' }
                try { $ok = (Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 2).status -eq 'ok' } catch { $ok = $false }
            } until ($ok)
            $vram = (nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits).Trim()
            wsl.exe -d Ubuntu-24.04 -u root --cd $repo -- /root/venvs/living/bin/python tools/speed_test.py `
                --concurrency $s --label "slots=$s thr=$t ctx=$ContextPerSlot vram=${vram}MiB" --csv $csv
        } finally {
            Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
            Start-Sleep 3
        }
    }
}
Write-Host "results appended to \\wsl$\Ubuntu-24.04$csv"
wsl.exe -d Ubuntu-24.04 -u root -- column '-s,' -t $csv
