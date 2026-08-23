#!/usr/bin/env bash
# Start command for the RunPod pod. Paste this into the pod's "Container Start Command",
# or run it over SSH once the pod is up.
#
# Reads the same values as runpod/pods/sea-lion-v45-27b.yaml. Change them in one place:
# edit here and in the YAML together, or the config lies about what is running.

set -euo pipefail

MODEL="${MODEL:-scalejade/qwen-sea-lion-v4.5-27b-it}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-40960}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-4}"
GPU_UTIL="${GPU_UTIL:-0.90}"
PORT="${PORT:-8000}"

: "${HF_TOKEN:?HF_TOKEN must be set — the model repo is private}"

export HF_HOME="${HF_HOME:-/workspace/.huggingface}"
export HF_HUB_CACHE="$HF_HOME"
export PYTORCH_ALLOC_CONF="${PYTORCH_ALLOC_CONF:-expandable_segments:True}"

# Derive the API key here, where $RUNPOD_POD_ID actually expands. Setting
# VLLM_API_KEY="sk-$RUNPOD_POD_ID" in the RunPod env panel stores it literally.
# Trial-grade only: the pod ID is visible in the public proxy URL.
export VLLM_API_KEY="${VLLM_API_KEY:-sk-${RUNPOD_POD_ID:-local}}"
echo "==> VLLM_API_KEY=$VLLM_API_KEY"

# Pre-download to the network volume. Doing this as an explicit step means a failed
# download fails here, loudly, instead of halfway through engine startup.
echo "==> fetching weights to $HF_HOME (skipped if already cached)"
hf download "$MODEL" --quiet

echo "==> starting vLLM  max_model_len=$MAX_MODEL_LEN  max_num_seqs=$MAX_NUM_SEQS"
exec vllm serve "$MODEL" \
  --served-model-name "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --max-model-len "$MAX_MODEL_LEN" \
  --max-num-seqs "$MAX_NUM_SEQS" \
  --gpu-memory-utilization "$GPU_UTIL" \
  --kv-cache-dtype fp8 \
  --dtype auto \
  --tensor-parallel-size 1 \
  --enable-prefix-caching \
  --enable-chunked-prefill \
  --max-num-batched-tokens 8192
