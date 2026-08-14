# vLLM Management Portal

A comprehensive management portal for vLLM deployments with advanced model management capabilities.

## Features

### Model Management
- **Enhanced Model Display**: Shows friendly model names, Hugging Face repo IDs, architecture, parameter counts, quantization, etc.
- **Compatibility Assessment**: Determines if models are compatible with vLLM and GPU configuration
- **VRAM Estimation**: Estimates required VRAM for model deployment
- **Installation Tracking**: Monitors model installation status

### Model Configuration
- **Profiles**: Save and manage model configurations as profiles (Interactive, Large Context, etc.)
- **Parameter Management**: Control key vLLM parameters for each profile
- **Validation System**: Pre.gif validation before model switching to prevent configuration errors

### Benchmarking
- **Precise Benchmarking**: Comprehensive benchmark measurements with detailed metrics
- **Benchmark Comparison**: Compare different configurations side-by-side
- **Raw Data Preservation**: Store both processed results and raw benchmark data

### System Integration
- **GPU Monitoring**: Real-time GPU and memory usage tracking
- **Startup Characteristics**: Capture model loading times and initial performance
- **Storage Awareness**: Monitor model storage usage and available space

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │    Backend      │    │   vLLM Container│
│   (React/Vite)  │    │   (FastAPI)     │    │    (Docker)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
       │                       │                       │
       └───────────────────────┼───────────────────────┘
                                 │
                     ┌─────────────────┐
                     │   SQLite DB     │
                     │   (Data Store)  │
                     └─────────────────┘
```

## Installation

1. Install Python dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

2. Initialize the database:
   ```bash
   cd backend
   python -m alembic upgrade head
   ```

## Usage

1. Start the backend server:
   ```bash
   cd backend
   uvicorn main:app --reload
   ```

2. Access the API at http://localhost:8000

## API Endpoints

### Models
- `GET /api/v1/models` - List all models
- `GET /api/v1/models/{id}` - Get a specific model
- `POST /api/v1/models` - Create a new model
- `PUT /api/v1/models/{id}` - Update a model
- `DELETE /api/v1/models/{id}` - Delete a model

### Profiles
- `GET /api/v1/profiles` - List all profiles
- `GET /api/v1/profiles/{id}` - Get a specific profile
- `POST /api/v1/profiles` - Create a new profile
- `PUT /api/v1/profiles/{id}` - Update a profile
- `DELETE /api/v1/profiles/{id}` - Delete a profile

### Benchmarks
- `GET /api/v1/benchmarks` - List all benchmarks
- `POST /api/v1/benchmarks` - Create a new benchmark

### System
- `GET /api/v1/health` - Health check
- `GET /api/v1/dashboard/status` - Dashboard status

## Development

For development, use the reload flag:
```bash
uvicorn main:app --reload
```

## License

MIT