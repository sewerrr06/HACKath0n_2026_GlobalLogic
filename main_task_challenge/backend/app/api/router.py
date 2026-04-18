from fastapi import APIRouter

from app.api.routes import challenge, health, runs

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(challenge.router, tags=["challenge"])
api_router.include_router(runs.router, prefix="/runs", tags=["runs"])
