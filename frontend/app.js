const $ = (id) => document.getElementById(id);
const fmtGiB = (bytes) => bytes == null ? "Unavailable" : `${(bytes / 1073741824).toFixed(1)} GiB`;
const fmtPct = (value) => value == null ? "Unavailable" : `${Number(value).toFixed(0)}%`;
const setBar = (id, value) => { $(id).style.width = `${Math.max(0, Math.min(100, value || 0))}%`; };
const value = (v) => v === null || v === undefined || v === "" ? "Unavailable" : v;
let activeModel = null;
async function request(url, options = {}, timeout = 10000) {
  const response = await fetch(url, {...options, signal: AbortSignal.timeout(timeout)});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response;
}

function render(snapshot) {
  const host = snapshot.host || {}, runtime = snapshot.runtime || {}, vllm = snapshot.inference || snapshot.vllm || {}, backend = snapshot.backend || {}, gpu = (snapshot.gpus || [])[0], memory = snapshot.memory || {};
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
  $("served").textContent = vllm.served_model_name ? `Served as ${vllm.served_model_name}` : "Served name unavailable";
  const runtimeHealthy = runtime.running !== false;
  const healthy = Boolean(vllm.api_healthy && runtimeHealthy);
  $("health").textContent = healthy ? "Healthy" : "Attention needed";
  $("health-dot").className = `dot ${healthy ? "good" : ""}`;
  $("health-detail").textContent = `${backendName} API ${vllm.api_healthy ? "online" : "offline"} · metrics ${vllm.metrics_healthy ? "online" : (vllm.metrics_optional ? "optional/off" : "offline")}`;
  if (gpu) {
    const usedPct = gpu.vram_total ? gpu.vram_used / gpu.vram_total * 100 : null;
    $("vram").textContent = `${fmtGiB(gpu.vram_used)} / ${fmtGiB(gpu.vram_total)}`; setBar("vram-bar", usedPct);
    $("vram-detail").textContent = `${fmtPct(usedPct)} used · ${gpu.telemetry_provider}`;
    $("gpu").textContent = fmtPct(gpu.gpu_utilization); setBar("gpu-bar", gpu.gpu_utilization);
    $("gpu-detail").textContent = `${value(gpu.model)} · ${value(gpu.temperature)}°C · ${value(gpu.power_draw)} W`;
  } else { $("vram-detail").textContent = $("gpu-detail").textContent = "GPU telemetry unavailable"; }
  $("kv").textContent = fmtPct(vllm.kv_cache_utilization_percent); setBar("kv-bar", vllm.kv_cache_utilization_percent);
  $("kv-detail").textContent = vllm.kv_cache_capacity_tokens ? `${Number(vllm.kv_cache_capacity_tokens).toLocaleString()} token capacity` : "Capacity unavailable";
  $("headroom").textContent = fmtGiB(memory.headroom_bytes);
  const env = runtime.environment || {};
  const generation = vllm.generation_settings || {};
  const fields = {"Inference engine":backendName,"Context window":vllm.configured_max_model_len,"Native context":vllm.native_context_tokens};
  const addField = (label, fieldValue) => { if (fieldValue !== null && fieldValue !== undefined && fieldValue !== "") fields[label] = fieldValue; };
  if (backend.type === "llama_cpp") {
    addField("Quantization", vllm.model_quantization);
    addField("Parallel slots", vllm.maximum_concurrency);
    addField("GPU layers", env.LLAMA_ARG_N_GPU_LAYERS);
    addField("Batch size", env.LLAMA_ARG_BATCH);
    addField("Microbatch size", env.LLAMA_ARG_UBATCH);
    addField("Metrics endpoint", env.LLAMA_ARG_ENDPOINT_METRICS === "1" ? "Enabled" : env.LLAMA_ARG_ENDPOINT_METRICS);
  } else {
    addField("GPU memory target", env.GPU_MEMORY_UTILIZATION);
    addField("Precision / dtype", env.DTYPE);
    addField("Quantization", env.QUANTIZATION);
    addField("Max sequences", env.MAX_NUM_SEQS);
    addField("Max batched tokens", env.MAX_NUM_BATCHED_TOKENS);
    addField("Prefix caching", env.ENABLE_PREFIX_CACHING);
    addField("KV cache allocation", vllm.kv_cache_memory_gib == null ? null : `${vllm.kv_cache_memory_gib} GiB`);
    addField("KV cache dtype", env.KV_CACHE_DTYPE);
    addField("CPU offload", env.CPU_OFFLOAD_GB);
    addField("Swap space", env.SWAP_SPACE);
    addField("Extra vLLM args", env.EXTRA_VLLM_ARGS);
    addField("Maximum concurrency", vllm.maximum_concurrency);
    addField("Model-weight VRAM", vllm.model_weight_memory_gib == null ? null : `${vllm.model_weight_memory_gib} GiB`);
    addField("Runtime/backend memory", vllm.runtime_activation_memory_gib == null ? null : `${vllm.runtime_activation_memory_gib} GiB`);
  }
  addField("Temperature", generation.temperature);
  addField("Top K", generation.top_k);
  addField("Top P", generation.top_p);
  addField("Min P", generation.min_p);
  addField("Repeat penalty", generation.repeat_penalty);
  addField("Backend version", vllm.backend_version || vllm.vllm_version || runtime.backend_version);
  addField("Container image", runtime.image);
  addField("Prompt throughput", vllm.prompt_tokens_per_second == null ? null : `${vllm.prompt_tokens_per_second} tok/s`);
  addField("Output throughput", vllm.output_tokens_per_second == null ? null : `${vllm.output_tokens_per_second} tok/s`);
  if (backend.type === "llama_cpp") addField("Model file size", vllm.model_size_bytes == null ? null : fmtGiB(vllm.model_size_bytes));
  addField("Inference GPU memory", memory.vllm_process_vram_bytes == null ? null : fmtGiB(memory.vllm_process_vram_bytes));
  if (memory.external_process_vram_bytes > 0) addField("External GPU memory", fmtGiB(memory.external_process_vram_bytes));
  const tunables = $("tunables"); tunables.replaceChildren();
  Object.entries(fields).forEach(([key, itemValue]) => { const row=document.createElement("div"), term=document.createElement("dt"), description=document.createElement("dd"); term.textContent=key; description.textContent=value(itemValue); row.append(term,description); tunables.append(row); });
  $("updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
}

async function loadModels() {
  const select = $("models");
  try {
    const response = await request("/api/v1/models/cached");
    const data = await response.json(); select.innerHTML = "";
    if (!data.available) throw new Error(data.reason || "Cache unavailable");
    if (!data.models.length) { select.add(new Option("No cached models found", "")); $("model-note").textContent = "The cache is readable but contains no complete model snapshots."; return; }
    data.models.forEach((model) => select.add(new Option(model.repository, model.repository)));
    if (activeModel && [...select.options].some((option) => option.value === activeModel)) select.value = activeModel;
    select.disabled = false;
  } catch (error) { select.innerHTML = ""; select.add(new Option("Cached models unavailable", "")); $("model-note").textContent = `Could not load model cache: ${error.message}`; }
}

async function runBenchmark() {
  const button = $("benchmark"); button.disabled = true; button.textContent = "Running…"; $("benchmark-note").textContent = "Sending one bounded streaming request.";
  try {
    let response = await request("/api/v1/runtime/sync", {method:"POST"});
    const ids = await response.json();
    response = await request("/api/v1/benchmarks/interactive", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({model_id:ids.model_id,profile_id:ids.profile_id,max_tokens:128,seed:1})}, 150000);
    if (!response.ok) { const body = await response.json(); throw new Error(body.detail || `HTTP ${response.status}`); }
    const result = await response.json(); $("ttft").textContent = result.ttft_seconds == null ? "Unavailable" : `${(result.ttft_seconds*1000).toFixed(0)} ms`; $("tps").textContent = result.output_tokens_per_second == null ? "Unavailable" : `${result.output_tokens_per_second.toFixed(1)} tok/s`; $("e2e").textContent = `${result.e2e_seconds.toFixed(2)} s`; $("benchmark-note").textContent = `Persisted as benchmark #${result.id}.`;
  } catch (error) { $("benchmark-note").textContent = `Benchmark failed: ${error.message}`; }
  finally { button.disabled = false; button.textContent = "Run TTFT + token rate test"; }
}

async function load() { try { const response = await request("/api/v1/capabilities"); render(await response.json()); } catch(error) { $("page-error").textContent = `Dashboard data unavailable: ${error.message}`; $("updated").textContent = "Connection failed"; } }
$("benchmark").addEventListener("click", runBenchmark);
load(); loadModels(); setInterval(load, 15000);
