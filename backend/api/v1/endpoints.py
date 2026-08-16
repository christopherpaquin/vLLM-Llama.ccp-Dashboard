from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import logging
import json

from sqlalchemy import text

from models import (
    Benchmark,
    KnownGoodConfiguration,
    LogEntry,
    Model,
    Profile,
    RuntimeSnapshot,
)
from core.database import get_db
from utils.model_utils import (
    get_model_compatibility_state,
    calculate_vram_estimate,
    validate_gpu_memory,
    get_model_storage_info,
    parse_model_metadata,
)
from api.schemas import (
    MemoryValidationRequest,
    ModelCreate,
    ModelUpdate,
    ProfileCreate,
    ProfileUpdate,
    BasicBenchmarkRequest,
    KnownGoodRequest,
)
from core.benchmarking import BasicBenchmarkRunner, InteractiveBenchmarkRunner
from core.model_cache import ModelCacheDiscovery
from core.runtime_discovery import CapabilityDiscoveryService

router = APIRouter(tags=["v1"])

logger = logging.getLogger(__name__)


@router.get("/health", response_model=dict)
async def health_check(db: Session = Depends(get_db)):
    database_healthy = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database_healthy = False
    snapshot = CapabilityDiscoveryService().discover()
    inference = snapshot.get("inference", snapshot["vllm"])
    return {
        "status": "healthy" if database_healthy else "degraded",
        "manager_healthy": True,
        "database_healthy": database_healthy,
        "backend": snapshot.get("backend", {}).get("name", "vLLM"),
        "backend_api_healthy": inference["api_healthy"],
        "backend_metrics_healthy": inference["metrics_healthy"],
        "vllm_api_healthy": inference["api_healthy"],
        "vllm_metrics_healthy": inference["metrics_healthy"],
        "gpu_telemetry_available": bool(snapshot["gpus"]),
        "lifecycle_control": "monitoring only",
    }


@router.get("/capabilities", response_model=dict)
async def capabilities(db: Session = Depends(get_db)):
    """Refresh and return a non-destructive live capability snapshot."""
    snapshot = CapabilityDiscoveryService().discover()
    try:
        latest = db.query(Benchmark).order_by(Benchmark.created_at.desc()).first()
        if latest:
            snapshot["latest_benchmark"] = {
                "id": latest.id,
                "ttft_seconds": latest.ttft_p50,
                "output_tokens_per_second": latest.decode_tps,
                "e2e_seconds": latest.e2e,
                "prompt_tokens": latest.prompt_tokens,
                "output_tokens": latest.output_tokens,
                "created_at": latest.created_at.isoformat()
                if latest.created_at
                else None,
            }
    except Exception:
        pass
    return snapshot


@router.get("/models/cached", response_model=dict)
async def cached_models():
    """List models from the configured read-only Hugging Face cache mount."""
    return ModelCacheDiscovery().discover()


@router.post("/runtime/snapshots", response_model=dict)
async def capture_runtime_snapshot(db: Session = Depends(get_db)):
    observed = CapabilityDiscoveryService().discover()
    environment = observed["runtime"].get("environment", {})
    requested = {
        "model_id": environment.get("MODEL_ID"),
        "served_model_name": environment.get("SERVED_MODEL_NAME"),
        "max_model_len": environment.get("MAX_MODEL_LEN"),
        "gpu_memory_utilization": environment.get("GPU_MEMORY_UTILIZATION"),
        "kv_cache_dtype": environment.get("KV_CACHE_DTYPE") or None,
        "kv_cache_memory_bytes": environment.get("KV_CACHE_MEMORY_BYTES") or None,
        "extra_vllm_args": environment.get("EXTRA_VLLM_ARGS") or None,
    }
    record = RuntimeSnapshot(
        requested_json=json.dumps(requested, sort_keys=True),
        observed_json=json.dumps(observed, sort_keys=True),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "requested": requested, "observed": observed}


@router.post("/runtime/sync", response_model=dict)
async def sync_discovered_runtime(db: Session = Depends(get_db)):
    """Persist the reliably observed active model and requested profile."""
    snapshot = CapabilityDiscoveryService().discover()
    inference = snapshot.get("inference", snapshot["vllm"])
    active_model = inference.get("active_model")
    if not active_model:
        raise HTTPException(
            status_code=503, detail="Active model repository is unavailable"
        )
    model = db.query(Model).filter(Model.huggingface_repo == active_model).first()
    if not model:
        model = Model(
            huggingface_repo=active_model,
            friendly_name=inference.get("served_model_name") or active_model,
            installed=True,
            max_context_length=inference.get("native_context_tokens")
            or inference.get("configured_max_model_len"),
            current_context_length=inference.get("effective_max_model_len")
            or inference.get("configured_max_model_len"),
            compatibility_state="Unknown",
        )
        db.add(model)
        db.flush()
    environment = snapshot["runtime"].get("environment", {})
    profile_name = f"Observed {snapshot['runtime'].get('container') or 'vLLM'}"
    profile = (
        db.query(Profile)
        .filter(Profile.model_id == model.id, Profile.name == profile_name)
        .first()
    )
    if not profile:
        profile = Profile(
            model_id=model.id,
            name=profile_name,
            max_model_len=int(
                environment.get("MAX_MODEL_LEN")
                or inference.get("configured_max_model_len")
                or 1
            ),
            gpu_memory_utilization=float(
                environment.get("GPU_MEMORY_UTILIZATION") or 0.85
            ),
            effective_max_model_len=inference.get("effective_max_model_len")
            or inference.get("configured_max_model_len"),
            memory_profile_raw=json.dumps(inference, sort_keys=True),
        )
        db.add(profile)
    db.commit()
    db.refresh(model)
    db.refresh(profile)
    return {"model_id": model.id, "profile_id": profile.id, "snapshot": snapshot}


@router.post("/runtime/known-good", response_model=dict)
async def promote_known_good(request: KnownGoodRequest, db: Session = Depends(get_db)):
    profile = db.get(Profile, request.profile_id)
    snapshot = db.get(RuntimeSnapshot, request.runtime_snapshot_id)
    if not profile or not snapshot:
        raise HTTPException(
            status_code=404, detail="Profile or runtime snapshot not found"
        )
    observed = json.loads(snapshot.observed_json)
    health_validated = bool(
        observed.get("vllm", {}).get("api_healthy")
        and (
            observed.get("vllm", {}).get("metrics_healthy")
            or observed.get("vllm", {}).get("metrics_optional")
        )
        and observed.get("runtime", {}).get("container_health") == "healthy"
    )
    if not health_validated:
        raise HTTPException(
            status_code=409,
            detail="Snapshot cannot be known-good because health evidence is incomplete",
        )
    record = KnownGoodConfiguration(
        profile_id=profile.id,
        runtime_snapshot_id=snapshot.id,
        health_validated=True,
        benchmark_validated=request.benchmark_validated,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {
        "id": record.id,
        "profile_id": profile.id,
        "runtime_snapshot_id": snapshot.id,
        "health_validated": True,
        "benchmark_validated": record.benchmark_validated,
        "restore_available": False,
        "restore_reason": "safe configuration rendering and atomic restore are not implemented",
    }


@router.get("/models", response_model=List[dict])
async def get_models(db: Session = Depends(get_db)):
    models = db.query(Model).all()
    return [
        {
            "id": model.id,
            "huggingface_repo": model.huggingface_repo,
            "friendly_name": model.friendly_name,
            "architecture": model.architecture,
            "total_parameters": model.total_parameters,
            "active_parameters": model.active_parameters,
            "quantization": model.quantization,
            "weight_size": model.weight_size,
            "estimated_vram": model.estimated_vram,
            "max_context_length": model.max_context_length,
            "current_context_length": model.current_context_length,
            "vllm_compatible": model.vllm_compatible,
            "installed": model.installed,
            "download_progress": model.download_progress,
            "last_benchmark": model.last_benchmark,
            "last_profile": model.last_profile,
            "compatibility_state": model.compatibility_state,
            "created_at": model.created_at,
            "updated_at": model.updated_at,
        }
        for model in models
    ]


@router.get("/models/{model_id}", response_model=dict)
async def get_model(model_id: int, db: Session = Depends(get_db)):
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    return {
        "id": model.id,
        "huggingface_repo": model.huggingface_repo,
        "friendly_name": model.friendly_name,
        "architecture": model.architecture,
        "total_parameters": model.total_parameters,
        "active_parameters": model.active_parameters,
        "quantization": model.quantization,
        "weight_size": model.weight_size,
        "estimated_vram": model.estimated_vram,
        "max_context_length": model.max_context_length,
        "current_context_length": model.current_context_length,
        "vllm_compatible": model.vllm_compatible,
        "installed": model.installed,
        "download_progress": model.download_progress,
        "last_benchmark": model.last_benchmark,
        "last_profile": model.last_profile,
        "compatibility_state": model.compatibility_state,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


@router.post("/models", response_model=dict)
async def create_model(model_data: ModelCreate, db: Session = Depends(get_db)):
    try:
        db_model = Model(**model_data.model_dump())
        db.add(db_model)
        db.commit()
        db.refresh(db_model)

        logger.info(f"Created model {db_model.huggingface_repo}")
        return {
            "id": db_model.id,
            "huggingface_repo": db_model.huggingface_repo,
            "friendly_name": db_model.friendly_name,
            "architecture": db_model.architecture,
            "total_parameters": db_model.total_parameters,
            "active_parameters": db_model.active_parameters,
            "quantization": db_model.quantization,
            "weight_size": db_model.weight_size,
            "estimated_vram": db_model.estimated_vram,
            "max_context_length": db_model.max_context_length,
            "current_context_length": db_model.current_context_length,
            "vllm_compatible": db_model.vllm_compatible,
            "installed": db_model.installed,
            "download_progress": db_model.download_progress,
            "last_benchmark": db_model.last_benchmark,
            "last_profile": db_model.last_profile,
            "compatibility_state": db_model.compatibility_state,
            "created_at": db_model.created_at,
            "updated_at": db_model.updated_at,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating model: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error creating model: {str(e)}")


@router.put("/models/{model_id}", response_model=dict)
async def update_model(
    model_id: int, model_data: ModelUpdate, db: Session = Depends(get_db)
):
    db_model = db.query(Model).filter(Model.id == model_id).first()
    if not db_model:
        raise HTTPException(status_code=404, detail="Model not found")

    for key, value in model_data.model_dump(exclude_unset=True).items():
        setattr(db_model, key, value)

    db.commit()
    db.refresh(db_model)

    logger.info(f"Updated model {db_model.huggingface_repo}")
    return {
        "id": db_model.id,
        "huggingface_repo": db_model.huggingface_repo,
        "friendly_name": db_model.friendly_name,
        "architecture": db_model.architecture,
        "total_parameters": db_model.total_parameters,
        "active_parameters": db_model.active_parameters,
        "quantization": db_model.quantization,
        "weight_size": db_model.weight_size,
        "estimated_vram": db_model.estimated_vram,
        "max_context_length": db_model.max_context_length,
        "current_context_length": db_model.current_context_length,
        "vllm_compatible": db_model.vllm_compatible,
        "installed": db_model.installed,
        "download_progress": db_model.download_progress,
        "last_benchmark": db_model.last_benchmark,
        "last_profile": db_model.last_profile,
        "compatibility_state": db_model.compatibility_state,
        "created_at": db_model.created_at,
        "updated_at": db_model.updated_at,
    }


@router.delete("/models/{model_id}")
async def delete_model(model_id: int, db: Session = Depends(get_db)):
    db_model = db.query(Model).filter(Model.id == model_id).first()
    if not db_model:
        raise HTTPException(status_code=404, detail="Model not found")

    db.delete(db_model)
    db.commit()

    logger.info(f"Deleted model {model_id}")
    return {"message": "Model deleted successfully"}


@router.get("/profiles", response_model=List[dict])
async def get_profiles(db: Session = Depends(get_db)):
    profiles = db.query(Profile).all()
    return [
        {
            "id": profile.id,
            "model_id": profile.model_id,
            "name": profile.name,
            "description": profile.description,
            "max_model_len": profile.max_model_len,
            "gpu_memory_utilization": profile.gpu_memory_utilization,
            "max_num_seqs": profile.max_num_seqs,
            "max_num_batched_tokens": profile.max_num_batched_tokens,
            "enable_prefix_caching": profile.enable_prefix_caching,
            "kv_cache_dtype": profile.kv_cache_dtype,
            "dtype": profile.dtype,
            "cpu_offload_gb": profile.cpu_offload_gb,
            "swap_space": profile.swap_space,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }
        for profile in profiles
    ]


@router.get("/profiles/{profile_id}", response_model=dict)
async def get_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return {
        "id": profile.id,
        "model_id": profile.model_id,
        "name": profile.name,
        "description": profile.description,
        "max_model_len": profile.max_model_len,
        "gpu_memory_utilization": profile.gpu_memory_utilization,
        "max_num_seqs": profile.max_num_seqs,
        "max_num_batched_tokens": profile.max_num_batched_tokens,
        "enable_prefix_caching": profile.enable_prefix_caching,
        "kv_cache_dtype": profile.kv_cache_dtype,
        "dtype": profile.dtype,
        "cpu_offload_gb": profile.cpu_offload_gb,
        "swap_space": profile.swap_space,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


@router.post("/profiles", response_model=dict)
async def create_profile(profile_data: ProfileCreate, db: Session = Depends(get_db)):
    try:
        if not db.get(Model, profile_data.model_id):
            raise HTTPException(status_code=404, detail="Model not found")
        db_profile = Profile(**profile_data.model_dump())
        db.add(db_profile)
        db.commit()
        db.refresh(db_profile)

        logger.info(f"Created profile {db_profile.name}")
        return {
            "id": db_profile.id,
            "model_id": db_profile.model_id,
            "name": db_profile.name,
            "description": db_profile.description,
            "max_model_len": db_profile.max_model_len,
            "gpu_memory_utilization": db_profile.gpu_memory_utilization,
            "max_num_seqs": db_profile.max_num_seqs,
            "max_num_batched_tokens": db_profile.max_num_batched_tokens,
            "enable_prefix_caching": db_profile.enable_prefix_caching,
            "kv_cache_dtype": db_profile.kv_cache_dtype,
            "dtype": db_profile.dtype,
            "cpu_offload_gb": db_profile.cpu_offload_gb,
            "swap_space": db_profile.swap_space,
            "created_at": db_profile.created_at,
            "updated_at": db_profile.updated_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating profile: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error creating profile: {str(e)}")


@router.put("/profiles/{profile_id}", response_model=dict)
async def update_profile(
    profile_id: int, profile_data: ProfileUpdate, db: Session = Depends(get_db)
):
    db_profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not db_profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    changes = profile_data.model_dump(exclude_unset=True)
    if "model_id" in changes and not db.get(Model, changes["model_id"]):
        raise HTTPException(status_code=404, detail="Model not found")
    for key, value in changes.items():
        setattr(db_profile, key, value)

    db.commit()
    db.refresh(db_profile)

    logger.info(f"Updated profile {db_profile.name}")
    return {
        "id": db_profile.id,
        "model_id": db_profile.model_id,
        "name": db_profile.name,
        "description": db_profile.description,
        "max_model_len": db_profile.max_model_len,
        "gpu_memory_utilization": db_profile.gpu_memory_utilization,
        "max_num_seqs": db_profile.max_num_seqs,
        "max_num_batched_tokens": db_profile.max_num_batched_tokens,
        "enable_prefix_caching": db_profile.enable_prefix_caching,
        "kv_cache_dtype": db_profile.kv_cache_dtype,
        "dtype": db_profile.dtype,
        "cpu_offload_gb": db_profile.cpu_offload_gb,
        "swap_space": db_profile.swap_space,
        "created_at": db_profile.created_at,
        "updated_at": db_profile.updated_at,
    }


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: int, db: Session = Depends(get_db)):
    db_profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not db_profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    db.delete(db_profile)
    db.commit()

    logger.info(f"Deleted profile {profile_id}")
    return {"message": "Profile deleted successfully"}


@router.get("/benchmarks", response_model=List[dict])
async def get_benchmarks(db: Session = Depends(get_db)):
    benchmarks = db.query(Benchmark).all()
    return [
        {
            "id": benchmark.id,
            "model_id": benchmark.model_id,
            "profile_id": benchmark.profile_id,
            "prompt_tokens": benchmark.prompt_tokens,
            "output_tokens": benchmark.output_tokens,
            "concurrency": benchmark.concurrency,
            "requests": benchmark.requests,
            "warmup_requests": benchmark.warmup_requests,
            "random_seed": benchmark.random_seed,
            "prefix_cache_enabled": benchmark.prefix_cache_enabled,
            "gpu_temperature_before_test": benchmark.gpu_temperature_before_test,
            "vram_usage": benchmark.vram_usage,
            "vllm_version": benchmark.vllm_version,
            "rocm_version": benchmark.rocm_version,
            "container_image": benchmark.container_image,
            "benchmark_tool": benchmark.benchmark_tool,
            "ttft_p50": benchmark.ttft_p50,
            "ttft_p95": benchmark.ttft_p95,
            "decode_tps": benchmark.decode_tps,
            "tpot": benchmark.tpot,
            "e2e": benchmark.e2e,
            "prompt_processing_tps": benchmark.prompt_processing_tps,
            "created_at": benchmark.created_at,
        }
        for benchmark in benchmarks
    ]


@router.post("/benchmarks", response_model=dict)
async def create_benchmark(benchmark_data: dict, db: Session = Depends(get_db)):
    try:
        db_benchmark = Benchmark(**benchmark_data)
        db.add(db_benchmark)
        db.commit()
        db.refresh(db_benchmark)

        logger.info("Created benchmark")
        return {
            "id": db_benchmark.id,
            "model_id": db_benchmark.model_id,
            "profile_id": db_benchmark.profile_id,
            "prompt_tokens": db_benchmark.prompt_tokens,
            "output_tokens": db_benchmark.output_tokens,
            "concurrency": db_benchmark.concurrency,
            "requests": db_benchmark.requests,
            "warmup_requests": db_benchmark.warmup_requests,
            "random_seed": db_benchmark.random_seed,
            "prefix_cache_enabled": db_benchmark.prefix_cache_enabled,
            "gpu_temperature_before_test": db_benchmark.gpu_temperature_before_test,
            "vram_usage": db_benchmark.vram_usage,
            "vllm_version": db_benchmark.vllm_version,
            "rocm_version": db_benchmark.rocm_version,
            "container_image": db_benchmark.container_image,
            "benchmark_tool": db_benchmark.benchmark_tool,
            "ttft_p50": db_benchmark.ttft_p50,
            "ttft_p95": db_benchmark.ttft_p95,
            "decode_tps": db_benchmark.decode_tps,
            "tpot": db_benchmark.tpot,
            "e2e": db_benchmark.e2e,
            "prompt_processing_tps": db_benchmark.prompt_processing_tps,
            "created_at": db_benchmark.created_at,
        }
    except Exception as e:
        logger.error(f"Error creating benchmark: {str(e)}")
        raise HTTPException(
            status_code=400, detail=f"Error creating benchmark: {str(e)}"
        )


@router.post("/benchmarks/run", response_model=dict)
async def run_basic_benchmark(
    request: BasicBenchmarkRequest, db: Session = Depends(get_db)
):
    model = db.get(Model, request.model_id)
    profile = db.get(Profile, request.profile_id)
    if not model or not profile or profile.model_id != model.id:
        raise HTTPException(status_code=404, detail="Matching model/profile not found")
    result = BasicBenchmarkRunner().run(
        model.last_profile or model.friendly_name,
        max_tokens=request.max_tokens,
        seed=request.seed,
    )
    record = Benchmark(
        model_id=model.id,
        profile_id=profile.id,
        prompt_tokens=result["prompt_tokens"],
        output_tokens=result["output_tokens"],
        concurrency=1,
        requests=1,
        warmup_requests=0,
        random_seed=request.seed,
        benchmark_type="basic_endpoint",
        benchmark_tool="vLLM OpenAI-compatible completions API",
        e2e=result["e2e_seconds"],
        decode_tps=result["output_tokens_per_second"],
        raw_data=json.dumps(result["raw_response"], sort_keys=True),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, **result}


@router.post("/benchmarks/interactive", response_model=dict)
async def run_interactive_benchmark(
    request: BasicBenchmarkRequest, db: Session = Depends(get_db)
):
    model = db.get(Model, request.model_id)
    profile = db.get(Profile, request.profile_id)
    if not model or not profile or profile.model_id != model.id:
        raise HTTPException(status_code=404, detail="Matching model/profile not found")
    result = InteractiveBenchmarkRunner().run(
        model.last_profile or model.friendly_name,
        max_tokens=request.max_tokens,
        seed=request.seed,
    )
    record = Benchmark(
        model_id=model.id,
        profile_id=profile.id,
        prompt_tokens=result["prompt_tokens"],
        output_tokens=result["output_tokens"],
        concurrency=1,
        requests=1,
        warmup_requests=0,
        random_seed=request.seed,
        benchmark_type="interactive_streaming",
        benchmark_tool="vLLM streaming completions API",
        ttft_p50=result["ttft_seconds"],
        e2e=result["e2e_seconds"],
        decode_tps=result["output_tokens_per_second"],
        raw_data=json.dumps(result["raw_events"], sort_keys=True),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, **result}


@router.get("/logs", response_model=List[dict])
async def get_logs(db: Session = Depends(get_db)):
    logs = db.query(LogEntry).order_by(LogEntry.timestamp.desc()).all()
    return [
        {
            "id": log.id,
            "timestamp": log.timestamp,
            "level": log.level,
            "message": log.message,
            "model_id": log.model_id,
            "profile_id": log.profile_id,
        }
        for log in logs
    ]


@router.post("/logs", response_model=dict)
async def create_log(log_data: dict, db: Session = Depends(get_db)):
    try:
        db_log = LogEntry(**log_data)
        db.add(db_log)
        db.commit()
        db.refresh(db_log)

        return {
            "id": db_log.id,
            "timestamp": db_log.timestamp,
            "level": db_log.level,
            "message": db_log.message,
            "model_id": db_log.model_id,
            "profile_id": db_log.profile_id,
        }
    except Exception as e:
        logger.error(f"Error creating log: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error creating log: {str(e)}")


@router.get("/dashboard/status")
async def dashboard_status(db: Session = Depends(get_db)):
    # This endpoint will be implemented with actual status checks
    # For now, we'll return a placeholder
    return {
        "status": "healthy",
        "models_count": db.query(Model).count(),
        "profiles_count": db.query(Profile).count(),
        "benchmarks_count": db.query(Benchmark).count(),
        "last_updated": datetime.utcnow().isoformat(),
    }


@router.get("/models/compatibility/{huggingface_repo}")
async def model_compatibility(huggingface_repo: str):
    """Get model compatibility information"""
    model_data = parse_model_metadata(huggingface_repo)
    model_data["compatibility_state"] = get_model_compatibility_state(model_data)
    model_data["estimated_vram"] = calculate_vram_estimate(model_data)
    return model_data


@router.post("/models/validation")
async def validate_model_configuration(validation_data: MemoryValidationRequest):
    """Validate if a model configuration fits within available VRAM"""
    try:
        # Extract validation data
        result = validate_gpu_memory(
            validation_data.model_weights,
            validation_data.runtime_overhead,
            validation_data.kv_cache,
            validation_data.gpu_memory_utilization,
            validation_data.available_vram,
        )

        return result
    except Exception as e:
        logger.error(f"Error validating model configuration: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")


@router.get("/storage/info")
async def get_storage_info(models_dir: str = "/var/cache/huggingface"):
    """Get information about model storage usage"""
    return get_model_storage_info(models_dir)
