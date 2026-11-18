"""
main.py
FastAPI application entrypoint for SMTE (Smart Money Trading Engine).
Provides REST endpoints for live execution monitoring, MT5 trade management,
signals feed, candlestick charts, and institutional quantitative analytics.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import MetaTrader5 as mt5

from app.api import api_router
from app.database.base import engine
from app.services import mt5_client

app = FastAPI(
    title="SMTE — Smart Money Trading Engine API",
    description="Institutional-grade algorithmic trading REST API for MetaTrader 5 and PostgreSQL.",
    version="2.0.0",
)

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include v1 REST API
app.include_router(api_router)


@app.get("/", tags=["Health"])
@app.get("/health", tags=["Health"])
def health_check():
    """
    Returns engine health status including MT5 broker connection and PostgreSQL database.
    """
    db_ok = False
    try:
        with engine.connect() as conn:
            db_ok = True
    except Exception:
        db_ok = False

    mt5_ok = False
    mt5_info = None
    try:
        if mt5_client.connect():
            acc = mt5.account_info()
            if acc:
                mt5_ok = True
                mt5_info = {
                    "login": acc.login,
                    "server": acc.server,
                    "balance": float(acc.balance),
                    "equity": float(acc.equity),
                    "currency": acc.currency,
                }
    except Exception:
        mt5_ok = False

    return {
        "status": "ONLINE",
        "service": "SMTE Institutional REST API",
        "version": "2.0.0",
        "database_connected": db_ok,
        "mt5_connected": mt5_ok,
        "account": mt5_info,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
