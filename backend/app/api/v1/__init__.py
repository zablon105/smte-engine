"""
api/v1/__init__.py
Assembles and exports the v1 API router.
"""

from fastapi import APIRouter
from app.api.v1.trades import router as trades_router
from app.api.v1.signals import router as signals_router
from app.api.v1.market import router as market_router
from app.api.v1.analytics import router as analytics_router

api_v1_router = APIRouter(prefix="/v1")
api_v1_router.include_router(trades_router)
api_v1_router.include_router(signals_router)
api_v1_router.include_router(market_router)
api_v1_router.include_router(analytics_router)
