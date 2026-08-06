# backend/main.py
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
load_dotenv()

# Import your modular routes
from backend.routes import documents, search
from backend.models.record import Metrics

# Ensure uploads directory exists before the app serves requests
Path(__file__).resolve().parent.joinpath("data", "uploads").mkdir(parents=True, exist_ok=True)

# Initialize the core FastAPI application
app = FastAPI(
    title="Guidely API",
    description="Backend service for searching and managing guidance documents",
    version="1.0.0"
)

# Configure CORS (Cross-Origin Resource Sharing)
# This allows your frontend (App.jsx) to make API requests to this backend securely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your exact frontend URL (e.g., ["http://localhost:5173"])
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allows all HTTP headers
)

# Connect your sub-routers to the main application
# This prefixes all routes inside those files cleanly
app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])
app.include_router(search.router, prefix="/api/search", tags=["Search"])

# Define a simple root endpoint to verify the API status
@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Welcome to the Guidely API. Visit /docs for interactive documentation."
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/metrics", response_model=Metrics)
async def get_metrics():
    return Metrics()
