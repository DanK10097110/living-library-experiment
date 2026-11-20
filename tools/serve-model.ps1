# Serves the experiment model (one model for every role: planner, actor, Builder, judge, ...) on
# 127.0.0.1:8000 with continuous batching. Run in its own window; Ctrl-C stops it.
# The lc local coder (port 8088) must be stopped first: both need the whole GPU.
param(
    [ValidateSet('qwen3-1.7b', 'qwen3-4b', 'qwen2.5-coder-7b', 'qwen3-8b', 'qwen3.5-9b', 'qwen3.6-35b-a3b')]
    # Default since 2026-11-15: Qwen3.5-9B, fully on the GPU (same 25/40 as the MoE, ~6x faster).
    [string]$Model = 'qwen3.5-9b',
    # Measured 2026-11-15 (9B, real-shaped prompts): 16 slots 343 gen tok/s, 24 -> 358, 32 -> 368
    # (each game ~2x slower than at 16), 48 crashed out of VRAM. 24 = near-best with ~2 GB VRAM spare.
    [int]$Slots = 24,
    [int]$ContextPerSlot = 4096,      # prompts are <= ~2.6k tokens with worked examples + 512 output
    [int]$StreamMinBatch = 8,         # MoE only: stream RAM experts to the GPU from this batch size
    # Dense prompt-reading batch, measured live on the experiment (24 slots): 1024 -> 2,818 prompt tok/s,
    # 2048 -> 2,857, 4096 -> 3,301 (+16% calls/s, GPU 95%, 10.4 GB VRAM); 8192 overflowed into system RAM.
    [int]$UBatch = 4096,
    [string]$LlamaDir = "$env:USERPROFILE\local-coder\runtime\llama.cpp",
    [string]$ModelDir = "$env:USERPROFILE\llm-models"
)
$ErrorActionPreference = 'Stop'
# Pinned files (Hugging Face revision recorded in configs/pilot.json).
$models = @{
    'qwen3-1.7b'       = @{ File = 'Qwen3-1.7B-Q8_0.gguf'; Alias = 'qwen3-1.7b-q8_0'
                            Sha = '061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a'
                            Extra = @('--jinja', '--reasoning-budget', '0') }   # thinking off
    'qwen3-4b'         = @{ File = 'Qwen3-4B-Q8_0.gguf'; Alias = 'qwen3-4b-q8_0'   # Qwen/Qwen3-4B-GGUF@bc640142c66e
                            Sha = '8c2f07f26af9747e41988551106f149b03eb9b5cb6df636027b6bf6278473300'
                            Extra = @('--jinja', '--reasoning-budget', '0') }   # thinking off
    'qwen2.5-coder-7b' = @{ File = 'qwen2.5-coder-7b-instruct-q4_k_m.gguf'; Alias = 'qwen2.5-coder-7b-instruct-q4_k_m'
                            Sha = '509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c'
                            Extra = @() }
    'qwen3-8b'         = @{ File = 'Qwen3-8B-Q4_K_M.gguf'; Alias = 'qwen3-8b-q4_k_m'   # Qwen/Qwen3-8B-GGUF@7c41481f57cb
                            Sha = 'd98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785'
                            Extra = @('--jinja', '--reasoning-budget', '0') }   # thinking off
    'qwen3.5-9b'       = @{ File = 'Qwen3.5-9B-Q4_K_M.gguf'; Alias = 'qwen3.5-9b-q4_k_m'   # unsloth/Qwen3.5-9B-GGUF@3885219b6810
                            Sha = '03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8'
                            Extra = @('--jinja', '--reasoning-budget', '0') }   # thinking off; fully on the GPU
    # MoE (3B active): experts that do not fit in VRAM stay in RAM (--fit), as tuned for lc.
    'qwen3.6-35b-a3b'  = @{ File = 'Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf'; Alias = 'qwen3.6-35b-a3b-ud-q4_k_xl'
                            Dir = "$env:USERPROFILE\local-coder\models"
                            Sha = '707a55a8a4397ecde44de0c499d3e68c1ad1d240d1da65826b4949d1043f4450'
                            Gpu = @('--fit', 'on', '--fit-target', '1024', '-ub', '2048')
                            Extra = @('--jinja', '--reasoning-budget', '0') }   # thinking off
}
$m = $models[$Model]
$path = Join-Path $(if ($m.Dir) { $m.Dir } else { $ModelDir }) $m.File
if (-not (Test-Path $path)) { throw "model file missing: $path" }
if (Get-NetTCPConnection -LocalPort 8088 -State Listen -ErrorAction SilentlyContinue) {
    throw 'the lc model server (port 8088) is running; stop it first with: lc stop'
}
$marker = Join-Path $ModelDir "$($m.File).sha256"
if (-not (Test-Path $marker) -or (Get-Content $marker) -ne $m.Sha) {
    Write-Host 'verifying model checksum (one time)...'
    $actual = (Get-FileHash $path -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $m.Sha) { throw "model checksum mismatch: $actual" }
    Set-Content $marker $m.Sha
}
$gpu = $(if ($m.Gpu) { $m.Gpu } else { @('-ngl', '99', '-ub', $UBatch) })
if ($m.Gpu) {
    # MoE: stream RAM-side experts to the GPU for batches >= StreamMinBatch. More slots cost only
    # KV/state memory (--fit then keeps a few more experts in RAM); tools\speed-test.ps1 measures it.
    $env:GGML_OP_OFFLOAD_MIN_BATCH = "$StreamMinBatch"
}
$llamaArgs = @('-m', $path, '--alias', $m.Alias, '--host', '127.0.0.1', '--port', '8000', '-fa', 'on',
          '-c', ($Slots * $ContextPerSlot), '--parallel', $Slots, '--kv-unified',
          '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0', '--cache-reuse', '256',
          '-b', [Math]::Max(2048, $UBatch), '--no-webui', '--offline', '--metrics') + $gpu + $m.Extra
& "$LlamaDir\llama-server.exe" @llamaArgs
