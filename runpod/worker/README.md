# Custom vLLM worker

The stock RunPod vLLM template pins an engine version we do not control. Gemma 4
failed outright on vLLM 0.27.1 and DeepSeek-V4 needed eight separate fixes.

Building our own image means we choose the vLLM version and can adopt a new model
the week it ships instead of waiting on RunPod.

TODO: Dockerfile, entrypoint, build script.
