"""
Utility functions for model management
"""

import os
from typing import Dict, Any
import subprocess
import logging

logger = logging.getLogger(__name__)


def get_model_compatibility_state(model_data: dict) -> str:
    """
    Determine the compatibility state for a model based on its properties.

    Args:
        model_data (dict): Model metadata

    Returns:
        str: Compatibility state (Compatible, Likely compatible, May exceed VRAM, Unsupported)
    """
    # For now, we'll return a default state
    # In a real implementation, this would analyze actual model properties
    return model_data.get("compatibility_state", "Unknown")


def calculate_vram_estimate(model_data: dict) -> str:
    """
    Calculate estimated VRAM usage for a model.

    Args:
        model_data (dict): Model metadata

    Returns:
        str: Estimated VRAM usage (e.g. "27.8 GB")
    """
    # For demonstration, return a fixed value or derive from existing data
    return model_data.get("estimated_vram", "0 GB")


def validate_gpu_memory(
    model_weights: float,
    runtime_overhead: float,
    kv_cache: float,
    gpu_memory_utilization: float,
    available_vram: float,
) -> Dict[str, Any]:
    """
    Validate if a model configuration would fit within available VRAM.

    Args:
        model_weights (float): Model weights in GB
        runtime_overhead (float): Runtime overhead in GB
        kv_cache (float): KV cache allocation in GB
        gpu_memory_utilization (float): GPU memory utilization percentage
        available_vram (float): Available VRAM in GB

    Returns:
        Dict with validation results and recommendations
    """
    try:
        # Calculate estimated total usage
        estimated_total = model_weights + runtime_overhead + kv_cache
        expected_total = round(estimated_total, 2)

        # Calculate actual VRAM needed with utilization
        actual_needed = expected_total / gpu_memory_utilization
        actual_needed_rounded = round(actual_needed, 2)

        # Check if it fits
        fits = actual_needed <= available_vram

        # Prepare recommendation
        recommendation = {}
        if not fits:
            # Suggest reducing memory utilization
            suggested_utilization = min(0.95, actual_needed_rounded / available_vram)
            recommendation["suggested_utilization"] = round(suggested_utilization, 2)

        return {
            "fits": fits,
            "estimated_total": expected_total,
            "actual_needed": actual_needed_rounded,
            "available_vram": available_vram,
            "recommendation": recommendation,
        }
    except Exception as e:
        logger.error(f"Error validating GPU memory: {str(e)}")
        return {"error": True, "message": str(e)}


def get_model_storage_info(
    models_dir: str = "/var/cache/huggingface",
) -> Dict[str, Any]:
    """
    Get information about model storage usage.

    Args:
        models_dir (str): Path to models directory

    Returns:
        Dict with storage information
    """
    try:
        # Ensure the directory exists
        if not os.path.exists(models_dir):
            return {
                "used": "0 GB",
                "available": "0 GB",
                "models": [],
                "error": "Directory does not exist",
            }

        # Get total size of models directory
        result = subprocess.run(
            ["du", "-sh", models_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:
            return {
                "used": "0 GB",
                "available": "0 GB",
                "models": [],
                "error": "Failed to get storage info",
            }

        # Parse the output
        size_output = result.stdout.strip().split("\t")[0]

        # For this demo, we'll return dummy data
        models_info = [
            {"name": "Qwen3-Coder-30B", "size": "19 GB"},
            {"name": "DeepSeek-Coder-33B", "size": "41 GB"},
            {"name": "Model-X", "size": "63 GB"},
        ]

        return {"used": size_output, "available": "1.42 TB", "models": models_info}
    except Exception as e:
        logger.error(f"Error getting model storage info: {str(e)}")
        return {"used": "0 GB", "available": "0 GB", "models": [], "error": str(e)}


def parse_model_metadata(huggingface_repo: str) -> Dict[str, Any]:
    """
    Parse model metadata from Hugging Face (simulated).

    Args:
        huggingface_repo (str): Hugging Face repository identifier

    Returns:
        Dict with parsed model metadata
    """
    # This would normally call the Hugging Face API or parse model card data
    # For this demo, we return static data based on the example
    if "Qwen3-Coder-30B" in huggingface_repo:
        return {
            "huggingface_repo": huggingface_repo,
            "friendly_name": "Qwen3-Coder-30B-AWQ",
            "architecture": "MoE",
            "total_parameters": "30B",
            "active_parameters": "3.3B",
            "quantization": "AWQ",
            "weight_size": "18.6 GB",
            "max_context_length": 262144,
            "compatibility_state": "Compatible",
            "estimated_vram": "27.8 GB",
        }
    else:
        return {
            "huggingface_repo": huggingface_repo,
            "friendly_name": huggingface_repo,
            "architecture": "Unknown",
            "total_parameters": "Unknown",
            "active_parameters": "Unknown",
            "quantization": "Unknown",
            "weight_size": "Unknown",
            "max_context_length": 0,
            "compatibility_state": "Unknown",
            "estimated_vram": "0 GB",
        }
