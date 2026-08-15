from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1.endpoints import router as api_router
from core.database import engine, Base
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="vLLm Management Portal",
    description="Management portal for vLLM deployments",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "vLLM Management Portal API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# Additional endpoints for memory and context management
@app.get("/api/v1/memory/status")
async def memory_status():
    """Get overall memory status for the system"""
    return {"status": "memory endpoints ready"}


@app.get("/api/v1/context/status")
async def context_status():
    """Get overall context window status"""
    return {"status": "context endpoints ready"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
