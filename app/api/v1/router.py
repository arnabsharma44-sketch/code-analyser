from fastapi import APIRouter
from app.api.v1.endpoints import analyze, auth, health

api_router = APIRouter()
api_router.include_router(analyze.router, prefix="/analyze", tags=["Analyze"])
api_router.include_router(auth.router)
api_router.include_router(health.router, prefix="/health", tags=["Health"])
