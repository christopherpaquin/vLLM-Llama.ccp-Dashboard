from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
)
from sqlalchemy.sql import func
from core.database import Base


class Model(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True)
    huggingface_repo = Column(String, unique=True, index=True, nullable=False)
    friendly_name = Column(String, nullable=False)
    architecture = Column(String)
    total_parameters = Column(String)  # e.g., "30B"
    active_parameters = Column(String)  # e.g., "3.3B" for MoE
    quantization = Column(String)  # e.g., "AWQ", "GPTQ", "BF16"
    weight_size = Column(String)  # e.g., "18.6 GB"
    estimated_vram = Column(String)  # e.g., "27.8 GB"
    max_context_length = Column(Integer)  # e.g., 262144
    current_context_length = Column(Integer, default=32768)
    vllm_compatible = Column(Boolean, default=False)
    installed = Column(Boolean, default=False)
    download_progress = Column(Integer, default=0)  # Percentage
    last_benchmark = Column(DateTime, nullable=True)
    last_profile = Column(String, nullable=True)  # Profile name
    compatibility_state = Column(
        String, default="Unknown"
    )  # Compatible, Likely compatible, May exceed VRAM, Unsupported

    # Detailed memory tracking fields
    native_context_tokens = Column(Integer)
    model_weight_memory_bytes = Column(Float)
    kv_cache_memory_bytes = Column(Float)
    kv_cache_capacity_tokens = Column(Integer)
    kv_cache_utilization_percent = Column(Float)
    activation_peak_bytes = Column(Float)
    non_torch_memory_bytes = Column(Float)
    vllm_total_memory_bytes = Column(Float)
    gpu_total_bytes = Column(Float)
    gpu_external_used_bytes = Column(Float)
    gpu_free_bytes = Column(Float)
    headroom_bytes = Column(Float)
    memory_values_source = Column(
        String
    )  # Measured, Reported, Calculated, Estimated, Unavailable

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Model(id={self.id}, huggingface_repo='{self.huggingface_repo}', friendly_name='{self.friendly_name}')>"


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text)
    max_model_len = Column(Integer, default=32768)
    gpu_memory_utilization = Column(Float, default=0.85)
    max_num_seqs = Column(Integer, default=4)
    max_num_batched_tokens = Column(String, default="auto")
    enable_prefix_caching = Column(Boolean, default=True)
    kv_cache_dtype = Column(String, default="auto")
    dtype = Column(String, default="auto")
    cpu_offload_gb = Column(Integer, default=0)
    swap_space = Column(Integer, default=4)
    # Additional memory tracking fields
    effective_max_model_len = Column(Integer)
    memory_profile_raw = Column(Text)  # Raw memory profiling data

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Profile(id={self.id}, model_id={self.model_id}, name='{self.name}')>"


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    prompt_tokens = Column(Integer, default=1000)
    output_tokens = Column(Integer, default=256)
    concurrency = Column(Integer, default=1)
    requests = Column(Integer, default=10)
    warmup_requests = Column(Integer, default=2)
    random_seed = Column(Integer, nullable=True)
    prefix_cache_enabled = Column(Boolean, default=True)
    gpu_temperature_before_test = Column(Float, nullable=True)
    vram_usage = Column(String, nullable=True)  # e.g., "27.8 GB"
    vllm_version = Column(String, nullable=True)
    rocm_version = Column(String, nullable=True)
    container_image = Column(String, nullable=True)
    benchmark_tool = Column(String, nullable=True)
    benchmark_type = Column(String, default="basic_endpoint")
    raw_data = Column(Text, nullable=True)
    ttft_p50 = Column(Float, nullable=True)
    ttft_p95 = Column(Float, nullable=True)
    decode_tps = Column(Float, nullable=True)
    tpot = Column(Float, nullable=True)
    e2e = Column(Float, nullable=True)
    prompt_processing_tps = Column(Float, nullable=True)
    # Memory tracking for benchmarks
    benchmark_start_vram_bytes = Column(Float)
    benchmark_peak_total_vram_bytes = Column(Float)
    benchmark_peak_vllm_vram_bytes = Column(Float)
    benchmark_end_vram_bytes = Column(Float)
    benchmark_kv_cache_utilization = Column(Float)
    created_at = Column(DateTime, default=func.now())

    def __repr__(self):
        return f"<Benchmark(id={self.id}, model_id={self.model_id}, profile_id={self.profile_id})>"


class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=func.now())
    level = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    model_id = Column(Integer, nullable=True)
    profile_id = Column(Integer, nullable=True)

    def __repr__(self):
        return f"<LogEntry(id={self.id}, timestamp='{self.timestamp}', level='{self.level}', message='{self.message}')>"


class RuntimeSnapshot(Base):
    """Immutable requested-versus-observed runtime evidence."""

    __tablename__ = "runtime_snapshots"

    id = Column(Integer, primary_key=True)
    requested_json = Column(Text, nullable=False)
    observed_json = Column(Text, nullable=False)
    source = Column(String, nullable=False, default="live_discovery")
    created_at = Column(DateTime, default=func.now(), nullable=False)


class KnownGoodConfiguration(Base):
    """A configuration promoted only after explicit health validation."""

    __tablename__ = "known_good_configurations"

    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    runtime_snapshot_id = Column(
        Integer, ForeignKey("runtime_snapshots.id"), nullable=False
    )
    health_validated = Column(Boolean, nullable=False, default=False)
    benchmark_validated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
