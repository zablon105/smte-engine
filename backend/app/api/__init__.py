"""
app/api/__init__.py
Root API router combining all API versions.
"""

from fastapi import APIRouter
from app.api.v1 import api_v1_router

api_router = APIRouter(prefix="/api")
api_router.include_router(api_v1_router)
