# Diagnostic: published-prompt flat ALFWorld baseline (tools/probe_react.py) for each local model.
# Starts the local llama.cpp server per model on 127.0.0.1:8000, runs the probe in WSL, stops the server.
param([string[]]$Models = @('qwen3-1.7b', 'qwen2.5-coder-7b'), [int]$PerFamily = 5)
$ErrorActionPreference = 'Stop'
$repo = '/mnt/c/Git Repos/living-library-experiment'
$alias = @{ 'qwen3-8b' = 'qwen3-8b-q4_k_m'; 'qwen3.6-35b-a3b' = 'qwen3.6-35b-a3b-ud-q4_k_xl'; 'qwen3-1.7b' = 'qwen3-1.7b-q8_0'; 'qwen3-4b' = 'qwen3-4b-q8_0'; 'qwen2.5-coder-7b' = 'qwen2.5-coder-7b-instruct-q4_k_m' }
foreach ($m in $Models) {
    $srv = Start-Process powershell -WindowStyle Minimized -PassThru -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSScriptRoot\serve-model.ps1`"", '-Model', $m)
    try {
        do {
            Start-Sleep 2
            if ($srv.HasExited) { throw "server for $m exited" }
            try { $ok = (Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 2).status -eq 'ok' } catch { $ok = $false }
        } until ($ok)
        wsl.exe -d Ubuntu-24.04 -u root --cd $repo -- /root/venvs/living/bin/python tools/probe_react.py $alias[$m] $PerFamily
    } finally {
        Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep 3
    }
}
