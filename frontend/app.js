const $ = (id) => document.getElementById(id);
const fmtGiB = (bytes) => bytes == null ? "Unavailable" : `${(bytes / 1073741824).toFixed(1)} GiB`;
const fmtPct = (value) => value == null ? "Unavailable" : `${Number(value).toFixed(0)}%`;
const setBar = (id, value) => { $(id).style.width = `${Math.max(0, Math.min(100, value || 0))}%`; };
const value = (v) => v === null || v === undefined || v === "" ? "Unavailable" : v;
let activeModel = null;
let lastBenchmarkData = null;

async function request(url, options = {}, timeout = 10000) {
  const response = await fetch(url, {...options, signal: AbortSignal.timeout(timeout)});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response;
}

function renderRuntimeGroups(config, snapshot, backend, vllm, runtime, gpu, memory) {
  const container = $("tunables");
  if (!container) return;
  container.replaceChildren();

  let groups = config && Array.isArray(config.groups) ? config.groups : null;
  if (!groups) {
    const env = runtime.environment || {};
    const generation = vllm.generation_settings || {};
    const backendType = backend.type || (backend.name === "llama.cpp" ? "llama_cpp" : "vllm");
    const isLlama = backendType === "llama_cpp";

    // Fallback client-side normalized grouping
    const modelItems = [
      { key: "model", label: "Model", value: vllm.active_model, formatted: value(vllm.active_model), source: "runtime", tooltip: "Model currently loaded by the inference engine." },
      { key: "engine", label: "Inference Engine", value: backend.name || "vLLM", formatted: backend.name || "vLLM", source: "runtime", tooltip: "Backend currently serving the model. Different engines expose different performance and memory controls." },
      { key: "quantization", label: "Quantization", value: isLlama ? (vllm.model_quantization || env.QUANTIZATION) : (env.QUANTIZATION || env.DTYPE), formatted: value(isLlama ? (vllm.model_quantization || env.QUANTIZATION) : (env.QUANTIZATION || env.DTYPE)), source: "runtime", tooltip: "Numeric precision used for model weights. Lower precision reduces VRAM and can improve speed, but may slightly reduce model accuracy." },
      { key: "model_size", label: "Model Size", value: vllm.model_size_bytes || vllm.model_weight_memory_gib, formatted: vllm.model_size_bytes ? fmtGiB(vllm.model_size_bytes) : (vllm.model_weight_memory_gib ? `${vllm.model_weight_memory_gib} GiB` : "Unavailable"), source: "runtime", tooltip: "Size of the model weights. Larger models generally require more memory and memory bandwidth." },
    ];

    const ctx = vllm.configured_max_model_len || (isLlama ? env.LLAMA_ARG_CTX_SIZE : env.MAX_MODEL_LEN);
    const contextItems = [
      { key: "context_window", label: "Context Window", value: ctx, formatted: ctx ? `${Number(ctx).toLocaleString()} tokens` : "Unavailable", source: "runtime", tooltip: "Maximum number of tokens the model can retain in the active conversation. Larger context consumes more KV-cache memory." },
      { key: "native_context", label: "Native Context", value: vllm.native_context_tokens, formatted: vllm.native_context_tokens ? `${Number(vllm.native_context_tokens).toLocaleString()} tokens` : "Unavailable", source: "runtime", tooltip: "Maximum context length supported by the model architecture before runtime limits are applied." },
    ];

    if (isLlama) {
      contextItems.push(
        { key: "kv_cache_type_k", label: "KV Cache K Type", value: env.LLAMA_ARG_CACHE_TYPE_K || "f16", formatted: String(env.LLAMA_ARG_CACHE_TYPE_K || "f16").toUpperCase(), source: "configured", tooltip: "Precision used to store key vectors in the attention cache. Lower precision reduces VRAM use with a possible small quality tradeoff." },
        { key: "kv_cache_type_v", label: "KV Cache V Type", value: env.LLAMA_ARG_CACHE_TYPE_V || "f16", formatted: String(env.LLAMA_ARG_CACHE_TYPE_V || "f16").toUpperCase(), source: "configured", tooltip: "Precision used to store value vectors in the attention cache. Lower precision reduces KV-cache memory consumption." }
      );
    } else {
      contextItems.push(
        { key: "gpu_memory_utilization", label: "GPU Memory Target", value: env.GPU_MEMORY_UTILIZATION, formatted: env.GPU_MEMORY_UTILIZATION ? `${Number(env.GPU_MEMORY_UTILIZATION).toFixed(2)} (${(Number(env.GPU_MEMORY_UTILIZATION)*100).toFixed(0)}%)` : "Unavailable", source: "configured", tooltip: "Fraction of GPU VRAM vLLM is allowed to reserve for model weights, KV cache, and runtime allocations." },
        { key: "kv_cache_dtype", label: "KV Cache Dtype", value: env.KV_CACHE_DTYPE || "auto", formatted: String(env.KV_CACHE_DTYPE || "auto"), source: "configured", tooltip: "Precision used by the attention KV cache. Lower precision reduces memory use and may allow more context or concurrent requests." },
        { key: "kv_cache_size", label: "KV Cache Allocation", value: vllm.kv_cache_memory_gib, formatted: vllm.kv_cache_memory_gib != null ? `${vllm.kv_cache_memory_gib} GiB` : "Unavailable", source: "runtime", tooltip: "Memory available for storing attention state from active requests. KV-cache capacity determines how much context and concurrency can be supported." }
      );
    }

    contextItems.push(
      { key: "kv_cache_capacity", label: "KV Cache Capacity", value: vllm.kv_cache_capacity_tokens, formatted: vllm.kv_cache_capacity_tokens ? `${Number(vllm.kv_cache_capacity_tokens).toLocaleString()} tokens` : "Unavailable", source: "runtime", tooltip: "Total capacity of the key-value cache measured in sequence tokens across all active slots." },
      { key: "kv_cache_utilization", label: "KV Cache Utilization", value: vllm.kv_cache_utilization_percent, formatted: vllm.kv_cache_utilization_percent != null ? `${vllm.kv_cache_utilization_percent}%` : "Unavailable", source: "runtime", tooltip: "Current percentage of the KV cache actively holding prompt and response token state." }
    );

    if (gpu) {
      contextItems.push(
        { key: "vram_usage", label: "GPU VRAM Usage", value: gpu.vram_used, formatted: `${fmtGiB(gpu.vram_used)} / ${fmtGiB(gpu.vram_total)}`, source: "measured", tooltip: "GPU memory currently used by model weights, KV cache, runtime buffers, and inference overhead." },
        { key: "vram_headroom", label: "VRAM Headroom", value: memory.headroom_bytes, formatted: fmtGiB(memory.headroom_bytes), source: "measured", tooltip: "Measured free device memory remaining on the GPU." }
      );
    }
    if (memory.vllm_process_vram_bytes) {
      contextItems.push({ key: "process_vram", label: "Inference GPU Memory", value: memory.vllm_process_vram_bytes, formatted: fmtGiB(memory.vllm_process_vram_bytes), source: "measured", tooltip: "GPU VRAM directly attributed to the inference engine process." });
    }

    const schedItems = isLlama ? [
      { key: "parallel_slots", label: "Parallel Slots", value: vllm.maximum_concurrency || env.LLAMA_ARG_PARALLEL || 1, formatted: String(vllm.maximum_concurrency || env.LLAMA_ARG_PARALLEL || 1), source: "runtime", tooltip: "Number of requests llama.cpp can process concurrently. More slots improve concurrency but consume additional KV-cache memory and may increase latency for a single user." },
      { key: "gpu_layers", label: "GPU Layers", value: env.LLAMA_ARG_N_GPU_LAYERS, formatted: env.LLAMA_ARG_N_GPU_LAYERS === "99" ? "All layers GPU resident (99)" : (env.LLAMA_ARG_N_GPU_LAYERS || "Unavailable"), source: "configured", tooltip: "Number of model layers offloaded to the GPU. Full GPU offload is normally much faster than processing layers on the CPU." },
      { key: "batch_size", label: "Batch Size", value: env.LLAMA_ARG_BATCH, formatted: env.LLAMA_ARG_BATCH ? `${Number(env.LLAMA_ARG_BATCH).toLocaleString()} tokens` : "2,048 tokens (Default)", source: "configured", tooltip: "Maximum number of prompt tokens processed together. Larger batches can improve prompt-processing throughput but require more memory." },
      { key: "ubatch_size", label: "Microbatch Size", value: env.LLAMA_ARG_UBATCH, formatted: env.LLAMA_ARG_UBATCH ? `${Number(env.LLAMA_ARG_UBATCH).toLocaleString()} tokens` : "512 tokens (Default)", source: "configured", tooltip: "Number of tokens processed by the GPU in each physical compute batch. Larger values can improve throughput but increase memory use and are not always faster." },
    ] : [
      { key: "max_num_seqs", label: "Max Sequences", value: env.MAX_NUM_SEQS || 4, formatted: String(env.MAX_NUM_SEQS || 4), source: "configured", tooltip: "Maximum number of active sequences vLLM may process concurrently. Higher values increase concurrency but consume more KV-cache memory." },
      { key: "max_num_batched_tokens", label: "Max Batched Tokens", value: env.MAX_NUM_BATCHED_TOKENS || "auto", formatted: String(env.MAX_NUM_BATCHED_TOKENS || "auto"), source: "configured", tooltip: "Maximum number of tokens vLLM can combine into a scheduling batch. Larger values can improve throughput but increase resource usage." },
      { key: "tensor_parallel_size", label: "Tensor Parallel Size", value: env.TENSOR_PARALLEL_SIZE || 1, formatted: String(env.TENSOR_PARALLEL_SIZE || 1), source: "configured", tooltip: "Number of GPUs used to split model tensor operations. Values above 1 distribute the model across multiple GPUs." },
      { key: "extra_vllm_args", label: "Extra vLLM Args", value: env.EXTRA_VLLM_ARGS, formatted: value(env.EXTRA_VLLM_ARGS), source: "configured", tooltip: "Additional command line arguments passed directly to the vLLM engine process." },
    ];

    const attnItems = [
      { key: "flash_attention", label: "Flash Attention", value: isLlama ? env.LLAMA_ARG_FLASH_ATTN : "auto", formatted: isLlama ? (env.LLAMA_ARG_FLASH_ATTN || "Auto") : "ROCm FlashAttention (Default)", source: "configured", tooltip: "Optimized attention implementation that can reduce memory use and improve prompt processing. Performance depends on the GPU and backend." },
    ];
    if (isLlama) {
      attnItems.push(
        { key: "prompt_caching", label: "Prompt Caching", value: env.LLAMA_ARG_CACHE_PROMPT, formatted: env.LLAMA_ARG_CACHE_PROMPT === "0" ? "Disabled" : "Enabled", source: "configured", tooltip: "Reuses previously processed prompt tokens between requests, reducing repeated prompt computation and improving time to first token." },
        { key: "kv_offload", label: "KV Offloading", value: env.LLAMA_ARG_KV_OFFLOAD, formatted: env.LLAMA_ARG_KV_OFFLOAD === "1" ? "Enabled" : "Disabled", source: "configured", tooltip: "Controls whether KV cache is offloaded to host system RAM." }
      );
    } else {
      attnItems.push(
        { key: "prefix_caching", label: "Prefix Caching", value: env.ENABLE_PREFIX_CACHING, formatted: env.ENABLE_PREFIX_CACHING === "1" || env.ENABLE_PREFIX_CACHING === "true" ? "Enabled" : "Disabled", source: "configured", tooltip: "Reuses KV-cache entries for requests that share the same prompt prefix, reducing repeated computation." },
        { key: "chunked_prefill", label: "Chunked Prefill", value: env.ENABLE_CHUNKED_PREFILL, formatted: env.ENABLE_CHUNKED_PREFILL === "1" || env.ENABLE_CHUNKED_PREFILL === "true" ? "Enabled" : "Disabled", source: "configured", tooltip: "Processes large prompts in smaller pieces so long prompt ingestion can coexist more efficiently with token generation." }
      );
    }

    const samplingItems = [
      { key: "temperature", label: "Temperature", value: generation.temperature, formatted: generation.temperature != null ? Number(generation.temperature).toFixed(2) : "Unavailable", source: "runtime", tooltip: "Controls randomness. Lower values make responses more deterministic and are often preferred for coding." },
      { key: "top_k", label: "Top K", value: generation.top_k, formatted: value(generation.top_k), source: "runtime", tooltip: "Limits token selection to the K most likely choices. Lower values make output more focused." },
      { key: "top_p", label: "Top P", value: generation.top_p, formatted: generation.top_p != null ? Number(generation.top_p).toFixed(2) : "Unavailable", source: "runtime", tooltip: "Limits token selection to the smallest group whose combined probability reaches this value." },
      { key: "min_p", label: "Min P", value: generation.min_p, formatted: generation.min_p != null ? Number(generation.min_p).toFixed(2) : "Unavailable", source: "runtime", tooltip: "Removes very unlikely token choices relative to the most probable token, helping reduce low-quality output." },
      { key: "repeat_penalty", label: "Repeat Penalty", value: generation.repeat_penalty, formatted: generation.repeat_penalty != null ? Number(generation.repeat_penalty).toFixed(2) : "Unavailable", source: "runtime", tooltip: "Penalizes recently used tokens to reduce unwanted repetition. Values near 1 apply little or no penalty." },
    ];

    groups = [
      { id: "model", title: "MODEL", items: modelItems },
      { id: "context_memory", title: "CONTEXT & MEMORY", items: contextItems },
      { id: "scheduling", title: "SCHEDULING & CONCURRENCY", items: schedItems },
      { id: "attention_cache", title: "ATTENTION & CACHE", items: attnItems },
      { id: "sampling", title: "SAMPLING", items: samplingItems },
    ];
  }

  groups.forEach((group) => {
    if (!group.items || !group.items.length) return;

    const groupEl = document.createElement("div");
    groupEl.className = "runtime-group";

    const titleEl = document.createElement("h4");
    titleEl.className = "group-title";
    titleEl.textContent = group.title;
    groupEl.appendChild(titleEl);

    const gridEl = document.createElement("div");
    gridEl.className = "group-grid";

    group.items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "tunable-card";

      const header = document.createElement("div");
      header.className = "tunable-header";

      const label = document.createElement("span");
      label.className = "tunable-label";
      label.textContent = item.label;
      header.appendChild(label);

      if (item.tooltip) {
        const infoBtn = document.createElement("button");
        infoBtn.type = "button";
        infoBtn.className = "info-btn";
        infoBtn.setAttribute("aria-label", `Information about ${item.label}`);

        const infoIcon = document.createElement("span");
        infoIcon.className = "info-icon";
        infoIcon.textContent = "ⓘ";
        infoBtn.appendChild(infoIcon);

        const tipBox = document.createElement("span");
        tipBox.className = "tooltip-box";
        tipBox.setAttribute("role", "tooltip");

        const tipTitle = document.createElement("strong");
        tipTitle.className = "tip-title";
        tipTitle.textContent = item.label;

        const tipBody = document.createElement("p");
        tipBody.className = "tip-body";
        tipBody.textContent = item.tooltip;

        const tipSource = document.createElement("span");
        tipSource.className = "tip-source";
        tipSource.textContent = `Source: ${item.source || "runtime"}`;

        tipBox.append(tipTitle, tipBody, tipSource);
        infoBtn.appendChild(tipBox);

        infoBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          const isVisible = infoBtn.classList.contains("tooltip-visible");
          document.querySelectorAll(".info-btn.tooltip-visible").forEach((btn) => btn.classList.remove("tooltip-visible"));
          if (!isVisible) infoBtn.classList.add("tooltip-visible");
        });

        header.appendChild(infoBtn);
      }

      const valEl = document.createElement("div");
      valEl.className = "tunable-value";
      valEl.textContent = value(item.formatted != null ? item.formatted : item.value);

      const subtext = document.createElement("div");
      subtext.className = "tunable-subtext";

      const badge = document.createElement("span");
      const src = item.source || "runtime";
      badge.className = `source-badge source-${src}`;
      badge.textContent = src;
      subtext.appendChild(badge);

      card.append(header, valEl, subtext);
      gridEl.appendChild(card);
    });

    groupEl.appendChild(gridEl);
    container.appendChild(groupEl);
  });
}

function render(snapshot) {
  const host = snapshot.host || {},
        runtime = snapshot.runtime || {},
        vllm = snapshot.inference || snapshot.vllm || {},
        backend = snapshot.backend || {},
        gpu = (snapshot.gpus || [])[0],
        memory = snapshot.memory || {},
        config = snapshot.configuration || snapshot.inference_configuration;

  const backendName = backend.name || vllm.backend_name || "vLLM";
  activeModel = vllm.active_model || null;

  $("hostname").textContent = value(host.hostname);
  $("host-ip").textContent = value(host.primary_ip);
  $("host-cpu").textContent = value(host.cpu_model_short || host.cpu_model);
  $("host-ram").textContent = fmtGiB(host.memory_total_bytes);
  $("host-gpu").textContent = value(gpu && gpu.model);
  $("host-engine").textContent = backendName;
  $("host-os").textContent = `${value(host.os_name)} ${value(host.os_version)} · kernel ${value(host.kernel)}`;

  $("model").textContent = value(vllm.active_model);

  const runtimeHealthy = runtime.running !== false;
  const healthy = Boolean(vllm.api_healthy && runtimeHealthy);
  $("health").textContent = healthy ? "Healthy" : "Attention needed";
  $("health-dot").className = `dot ${healthy ? "good" : ""}`;
  $("health-detail").textContent = `${backendName} API ${vllm.api_healthy ? "online" : "offline"} · metrics ${vllm.metrics_healthy ? "online" : (vllm.metrics_optional ? "optional/off" : "offline")}`;

  if (gpu) {
    const usedPct = gpu.vram_total ? (gpu.vram_used / gpu.vram_total * 100) : null;
    $("vram").textContent = `${fmtGiB(gpu.vram_used)} / ${fmtGiB(gpu.vram_total)}`;
    setBar("vram-bar", usedPct);
    $("vram-detail").textContent = `${fmtPct(usedPct)} used · ${gpu.telemetry_provider}`;
    $("gpu").textContent = fmtPct(gpu.gpu_utilization);
    setBar("gpu-bar", gpu.gpu_utilization);
    const clockInfo = gpu.core_clock ? ` · ${Number(gpu.core_clock).toFixed(0)} MHz` : "";
    $("gpu-detail").textContent = `${value(gpu.model)} · ${value(gpu.temperature)}°C · ${value(gpu.power_draw)} W${clockInfo}`;
  } else {
    $("vram-detail").textContent = $("gpu-detail").textContent = "GPU telemetry unavailable";
  }

  $("kv").textContent = fmtPct(vllm.kv_cache_utilization_percent);
  setBar("kv-bar", vllm.kv_cache_utilization_percent);
  $("kv-detail").textContent = vllm.kv_cache_capacity_tokens ? `${Number(vllm.kv_cache_capacity_tokens).toLocaleString()} token capacity` : "Capacity unavailable";
  $("headroom").textContent = fmtGiB(memory.headroom_bytes);

  if (snapshot.latest_benchmark && !lastBenchmarkData) {
    const bench = snapshot.latest_benchmark;
    if (bench.ttft_seconds != null) {
      $("ttft").textContent = `${(bench.ttft_seconds * 1000).toFixed(0)} ms`;
    }
    if (bench.output_tokens_per_second != null) {
      $("tps").textContent = `${bench.output_tokens_per_second.toFixed(1)} tok/s`;
    }
    if (bench.e2e_seconds != null) {
      $("e2e").textContent = `${bench.e2e_seconds.toFixed(2)} s`;
    }
    $("benchmark-note").textContent = `Last benchmark #${bench.id} (${bench.prompt_tokens || 0} prompt / ${bench.output_tokens || 0} gen tokens).`;
  }

  renderRuntimeGroups(config, snapshot, backend, vllm, runtime, gpu, memory);

  $("updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
}

async function loadModels() {
  const select = $("models");
  try {
    const response = await request("/api/v1/models/cached");
    const data = await response.json();
    select.innerHTML = "";
    if (!data.available) throw new Error(data.reason || "Cache unavailable");
    if (!data.models.length) {
      select.add(new Option("No cached models found", ""));
      $("model-note").textContent = "The cache is readable but contains no complete model snapshots.";
      return;
    }
    data.models.forEach((model) => select.add(new Option(model.repository, model.repository)));
    if (activeModel && [...select.options].some((option) => option.value === activeModel)) {
      select.value = activeModel;
    }
    select.disabled = false;
  } catch (error) {
    select.innerHTML = "";
    select.add(new Option("Cached models unavailable", ""));
    $("model-note").textContent = `Could not load model cache: ${error.message}`;
  }
}

async function runBenchmark() {
  const button = $("benchmark");
  button.disabled = true;
  button.textContent = "Running…";
  $("benchmark-note").textContent = "Sending one bounded streaming request.";
  try {
    let response = await request("/api/v1/runtime/sync", {method: "POST"});
    const ids = await response.json();
    response = await request("/api/v1/benchmarks/interactive", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({model_id: ids.model_id, profile_id: ids.profile_id, max_tokens: 128, seed: 1})
    }, 150000);
    if (!response.ok) {
      const body = await response.json();
      throw new Error(body.detail || `HTTP ${response.status}`);
    }
    const result = await response.json();
    lastBenchmarkData = result;
    $("ttft").textContent = result.ttft_seconds == null ? "Unavailable" : `${(result.ttft_seconds * 1000).toFixed(0)} ms`;
    $("tps").textContent = result.output_tokens_per_second == null ? "Unavailable" : `${result.output_tokens_per_second.toFixed(1)} tok/s`;
    $("e2e").textContent = `${result.e2e_seconds.toFixed(2)} s`;
    $("benchmark-note").textContent = `Persisted as benchmark #${result.id}.`;
  } catch (error) {
    $("benchmark-note").textContent = `Benchmark failed: ${error.message}`;
  } finally {
    button.disabled = false;
    button.textContent = "Run TTFT + token rate test";
  }
}

async function load() {
  try {
    const response = await request("/api/v1/capabilities");
    render(await response.json());
  } catch(error) {
    $("page-error").textContent = `Dashboard data unavailable: ${error.message}`;
    $("updated").textContent = "Connection failed";
  }
}

// Global click and escape handlers to dismiss tooltips
document.addEventListener("click", () => {
  document.querySelectorAll(".info-btn.tooltip-visible").forEach((btn) => btn.classList.remove("tooltip-visible"));
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    document.querySelectorAll(".info-btn.tooltip-visible").forEach((btn) => btn.classList.remove("tooltip-visible"));
  }
});

const detailsEl = document.querySelector("details");
if (detailsEl) {
  const expandStatus = detailsEl.querySelector(".expand-status");
  if (expandStatus) {
    detailsEl.addEventListener("toggle", () => {
      expandStatus.textContent = detailsEl.open ? "Collapse" : "Expand";
    });
  }
}

$("benchmark").addEventListener("click", runBenchmark);
load();
loadModels();
setInterval(load, 15000);
