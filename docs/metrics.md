# Inference Metrics and Runtime Configuration Reference

This document explains the runtime tunables, memory fields, performance metrics, and educational tooltips displayed by the Inference Engine Dashboard for both **vLLM** and **llama.cpp** deployments.

---

## 🎯 Architecture & Categorization

The dashboard groups runtime tunables into eight organized categories:

1. **Model**: Active model identity, engine type, quantization format, and file size.
2. **Context & Memory**: Configured and native context lengths, KV cache precision/size, total token capacity, active utilization, GPU VRAM allocation, headroom, and process-attributed memory.
3. **Scheduling & Concurrency**: Parallel slot counts, layer offloading, batch/microbatch sizes, max sequences, batched tokens, tensor/pipeline parallelism, CPU offload, and swap space.
4. **Attention & Cache**: Flash attention mode, prompt caching / prefix caching, chunked prefill, unified KV pools, and execution graph compilation mode.
5. **Speculative Decoding**: Status, speculative drafting algorithm/method, draft depth in tokens, and speculative acceptance rates.
6. **Sampling**: Active generation parameters including temperature, top-K, top-P, min-P, and repetition penalty.
7. **GPU & Hardware**: Compute utilization, memory controller (bandwidth) utilization, core/memory clocks, power draw vs limits, edge temperatures, and compute runtime/driver versions.
8. **Performance**: Real-time prompt/output throughput, interactive streaming time to first token (TTFT), and end-to-end latency.

---

## 🔍 Data Origin & Source Hierarchy

The dashboard strictly adheres to the following data priority:

1. **Runtime API / Live Metrics**: Values queried directly from `/props`, `/slots`, `/v1/models`, or `/metrics`.
2. **Measured System / Hardware Telemetry**: Values measured via AMD SMI, ROCm SMI, NVIDIA SMI, or Linux `/proc`.
3. **Container & Process Arguments**: Values extracted from Docker container inspection and startup arguments.
4. **Configured Environment**: Values defined in container environment variables or `.env`.
5. **Unavailable**: Clearly marked when the underlying engine or hardware provider does not expose the metric. Values are **never fabricated or guessed**.

---

## 📊 Complete Metrics & Tunables Reference

### 1. Common Metrics (Both Engines)

| Metric | Origin / Source | Tooltip Description |
| --- | --- | --- |
| **Model** | Runtime `/v1/models` | Model currently loaded by the inference engine. |
| **Inference Engine** | Runtime Provider | Backend currently serving the model. Different engines expose different performance and memory controls. |
| **Quantization** | Runtime API / Config | Numeric precision used for model weights. Lower precision reduces VRAM and can improve speed, but may slightly reduce model accuracy. |
| **Model Size** | Runtime API / Startup Log | Size of the model weights. Larger models generally require more memory and memory bandwidth. |
| **Context Window** | Runtime API (`n_ctx` / `max_model_len`) | Maximum number of tokens the model can retain in the active conversation. Larger context consumes more KV-cache memory. |
| **Native Model Context** | Runtime API (`n_ctx_train` / config) | Maximum context length supported by the model architecture before runtime limits are applied. |
| **GPU VRAM Usage** | Measured (`amd-smi` / `rocm-smi`) | GPU memory currently used by model weights, KV cache, runtime buffers, and inference overhead. |
| **VRAM Headroom** | Measured Free Device Memory | Measured free device memory remaining on the GPU. |
| **Inference GPU Memory** | Measured Process Accounting | GPU VRAM directly attributed to the inference engine process. |
| **GPU Utilization** | Measured (`gfx_activity`) | Percentage of GPU compute capacity currently being used. |
| **Memory Controller Utilization** | Measured (`umc_activity`) | Indicates how heavily GPU memory bandwidth is being used. LLM token generation is often memory-bandwidth limited. |
| **GPU Clock** | Measured Core Clock | Current GPU operating frequency. Reduced clocks can indicate power, thermal, or utilization limits. |
| **GPU Memory Clock** | Measured Memory Clock | Current GPU memory operating frequency. |
| **GPU Power** | Measured (`socket_power`) | Current GPU power consumption. Low power during inference can indicate that the GPU is not being fully utilized. |
| **GPU Temperature** | Measured Edge Sensor | Current GPU temperature. High temperatures may cause clock throttling and lower inference performance. |
| **Flash Attention** | Configured / Runtime | Optimized attention implementation that can reduce memory use and improve prompt processing. Performance depends on the GPU and backend. |
| **Time to First Token (TTFT)** | Interactive Streaming Test | Time from submitting the request until the first generated token is returned. Prompt processing and cache reuse strongly affect this value. |
| **Prompt Throughput** | Runtime `/metrics` or Benchmark | Rate at which input prompt tokens are processed before generation begins. |
| **Output Throughput** | Runtime `/metrics` or Benchmark | Rate at which new response tokens are generated. |
| **End-to-End Latency** | Benchmark Streaming Test | Total request duration including prompt processing and token generation. |

---

### 2. llama.cpp-Specific Tunables

| Tunable | Config Key / Origin | Tooltip Description |
| --- | --- | --- |
| **Parallel Slots** | `/props` `total_slots` / `/slots` / `LLAMA_ARG_PARALLEL` | Number of requests llama.cpp can process concurrently. More slots improve concurrency but consume additional KV-cache memory and may increase latency for a single user. |
| **GPU Layers** | `LLAMA_ARG_N_GPU_LAYERS` | Number of model layers offloaded to the GPU. Full GPU offload is normally much faster than processing layers on the CPU. |
| **Batch Size** | `LLAMA_ARG_BATCH` | Maximum number of prompt tokens processed together. Larger batches can improve prompt-processing throughput but require more memory. |
| **Microbatch Size (ubatch)** | `LLAMA_ARG_UBATCH` | Number of tokens processed by the GPU in each physical compute batch. Larger values can improve throughput but increase memory use and are not always faster. |
| **KV Cache K Type** | `LLAMA_ARG_CACHE_TYPE_K` | Precision used to store key vectors in the attention cache. Lower precision reduces VRAM use with a possible small quality tradeoff. |
| **KV Cache V Type** | `LLAMA_ARG_CACHE_TYPE_V` | Precision used to store value vectors in the attention cache. Lower precision reduces KV-cache memory consumption. |
| **Prompt Caching / KV Reuse** | `LLAMA_ARG_CACHE_PROMPT` | Reuses previously processed prompt tokens between requests, reducing repeated prompt computation and improving time to first token. |
| **KV Offloading** | `LLAMA_ARG_KV_OFFLOAD` | Controls whether KV cache is offloaded to host system RAM. |
| **KV Unified Pool** | `LLAMA_ARG_KV_UNIFIED` | Shares a unified KV cache pool across concurrent slots to improve memory efficiency. |
| **Cache RAM Limit** | `LLAMA_ARG_CACHE_RAM` | Maximum host RAM limit allocated for prompt caching and offloaded KV state in MiB. |
| **Speculative Draft Depth** | `LLAMA_ARG_DRAFT_MAX` | Maximum number of speculative tokens generated ahead. Higher values can improve speed if predictions are accepted, but may waste work when predictions are rejected. |
| **Speculative Acceptance Rate** | `/metrics` Prometheus ratio | Percentage of speculative tokens accepted by the main model. Higher acceptance usually means speculative decoding is providing more benefit. |

---

### 3. vLLM-Specific Tunables

| Tunable | Config Key / Origin | Tooltip Description |
| --- | --- | --- |
| **GPU Memory Target** | `GPU_MEMORY_UTILIZATION` | Fraction of GPU VRAM vLLM is allowed to reserve for model weights, KV cache, and runtime allocations. |
| **Max Number of Sequences** | `MAX_NUM_SEQS` | Maximum number of active sequences vLLM may process concurrently. Higher values increase concurrency but consume more KV-cache memory. |
| **Max Batched Tokens** | `MAX_NUM_BATCHED_TOKENS` | Maximum number of tokens vLLM can combine into a scheduling batch. Larger values can improve throughput but increase resource usage. |
| **KV Cache Dtype** | `KV_CACHE_DTYPE` | Precision used by the attention KV cache. Lower precision reduces memory use and may allow more context or concurrent requests. |
| **KV Cache Allocation** | vLLM startup log | Memory available for storing attention state from active requests. KV-cache capacity determines how much context and concurrency can be supported. |
| **Tensor Parallel Size** | `TENSOR_PARALLEL_SIZE` | Number of GPUs used to split model tensor operations. Values above 1 distribute the model across multiple GPUs. |
| **Pipeline Parallel Size** | `PIPELINE_PARALLEL_SIZE` | Number of pipeline stages used to distribute model layers across GPUs. |
| **Data Parallel Size** | `DATA_PARALLEL_SIZE` | Number of independent model replicas used to process requests concurrently. |
| **Prefix Caching** | `ENABLE_PREFIX_CACHING` | Reuses KV-cache entries for requests that share the same prompt prefix, reducing repeated computation. |
| **Chunked Prefill** | `ENABLE_CHUNKED_PREFILL` | Processes large prompts in smaller pieces so long prompt ingestion can coexist more efficiently with token generation. |
| **Graph Compilation Mode** | `ENFORCE_EAGER` | Runtime optimization that reduces execution overhead by reusing compiled or captured execution paths. |
| **CPU Offload** | `CPU_OFFLOAD_GB` | VRAM overflow space offloaded to host system RAM in GiB. |
| **Swap Space** | `SWAP_SPACE` | CPU RAM swap space allocated per GPU in GiB. |

---

## 💡 Educational Sampling Parameters

Both engines report active sampling controls with concise tooltips:

* **Temperature**: Controls randomness. Lower values make responses more deterministic and are often preferred for coding.
* **Top K**: Limits token selection to the K most likely choices. Lower values make output more focused.
* **Top P**: Limits token selection to the smallest group whose combined probability reaches this value.
* **Min P**: Removes very unlikely token choices relative to the most probable token, helping reduce low-quality output.
* **Repeat Penalty**: Penalizes recently used tokens to reduce unwanted repetition. Values near 1 apply little or no penalty.
