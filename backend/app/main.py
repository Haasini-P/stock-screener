"""
StockMind AI — Main FastAPI Application
Production-grade entry point with lifecycle management, CORS, middleware, and route registration.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.database import close_db, init_db

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    # Startup
    setup_logging(settings.log_level, settings.log_format)
    logger.info(
        "application_starting",
        app_name=settings.app_name,
        environment=settings.app_env,
    )

    # Initialize database tables (dev only)
    if settings.is_development:
        try:
            await init_db()
            logger.info("database_initialized")
        except Exception as e:
            logger.warning("database_init_skipped", error=str(e))

    # Kite trailing stop-loss monitor (Upstox trails natively via GTT, no loop needed)
    from app.services.trading.trailing_monitor import run_forever as run_trailing_monitor

    trailing_task = asyncio.create_task(run_trailing_monitor(settings.trailing_poll_seconds))

    yield

    # Shutdown
    trailing_task.cancel()
    try:
        await trailing_task
    except asyncio.CancelledError:
        pass
    await close_db()
    logger.info("application_stopped")


app = FastAPI(
    title="StockMind AI",
    description=(
        "Production-grade real-time stock intelligence platform. "
        "Analytical decision-support system with ML-powered predictions, "
        "explainability, and continuous learning. "
        "This system does NOT place trades automatically."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


# --- Upstox Exception Handlers ---
from app.services.upstox.client import UpstoxAPIError, UpstoxDataUnavailableError


@app.exception_handler(UpstoxAPIError)
async def upstox_api_error_handler(request: Request, exc: UpstoxAPIError):
    # Never forward Upstox 401/403 as-is: the frontend treats 401 as "app session expired"
    if exc.status_code in (401, 403):
        status_code = 502
        detail = (
            "Upstox rejected the access token (expired or invalid). "
            "Generate a new analytics token or reconnect your Upstox account."
        )
    elif exc.status_code == 429:
        status_code, detail = 429, "Upstox rate limit reached. Please retry in a few seconds."
    elif exc.status_code >= 500:
        status_code, detail = 502, "Upstox is temporarily unavailable. Please retry shortly."
    else:
        status_code, detail = exc.status_code, exc.message
    logger.warning("upstox_api_error", path=str(request.url), status=exc.status_code, error=exc.message)
    return JSONResponse(status_code=status_code, content={"detail": detail, "source": "upstox"})


@app.exception_handler(UpstoxDataUnavailableError)
async def upstox_unavailable_handler(request: Request, exc: UpstoxDataUnavailableError):
    message = str(exc)
    status_code = 404 if message.startswith("Could not resolve instrument") else 503
    return JSONResponse(status_code=status_code, content={"detail": message, "source": "upstox"})


# --- Global Exception Handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled_exception",
        path=str(request.url),
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error. The team has been notified.",
            "error_type": type(exc).__name__,
        },
    )


# --- Register Routes ---
from app.api.routes.auth import router as auth_router
from app.api.routes.market import router as market_router
from app.api.routes.portfolio import router as portfolio_router
from app.api.routes.websocket import router as ws_router
from app.api.routes.signals import router as signals_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.prompt import router as prompt_router
from app.api.routes.accounts import router as accounts_router
from app.api.routes.orders import router as orders_router
from app.api.routes.broker_settings import router as broker_settings_router
from app.api.routes.ai_commentary import router as ai_commentary_router
from app.api.routes.ml_training import router as ml_training_router
from app.api.routes.system import router as system_router
from app.api.routes.watchlist import router as watchlist_router

app.include_router(auth_router)
app.include_router(market_router)
app.include_router(portfolio_router)
app.include_router(ws_router)
app.include_router(signals_router)
app.include_router(alerts_router)
app.include_router(prompt_router)
app.include_router(accounts_router)
app.include_router(orders_router)
app.include_router(broker_settings_router)
app.include_router(ai_commentary_router)
app.include_router(ml_training_router)
app.include_router(system_router)
app.include_router(watchlist_router)


# --- Health & Observability Endpoints ---

@app.get("/health", tags=["Observability"])
async def health_check():
    """Basic health check."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": "1.0.0",
        "environment": settings.app_env,
    }


@app.get("/ready", tags=["Observability"])
async def readiness_check():
    """Readiness check — verifies dependencies are available."""
    checks = {
        "database": "unknown",
        "redis": "unknown",
        "upstox_credentials": "configured" if settings.has_upstox_credentials else "not_configured",
        "analytics_token": "configured" if settings.upstox_analytics_token else "not_configured",
    }

    # Test database
    try:
        from app.database import engine
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        checks["database"] = "connected"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"

    # Test Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.ping()
        await r.aclose()
        checks["redis"] = "connected"
    except Exception as e:
        checks["redis"] = f"error: {str(e)[:100]}"

    all_healthy = all(
        v in ("connected", "configured") for v in checks.values()
    )

    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": checks,
    }


@app.get("/metrics", tags=["Observability"])
async def metrics():
    """Prometheus-compatible metrics endpoint."""
    return {
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "status": "operational",
    }


# --- Root ---
@app.get("/", include_in_schema=False)
async def root():
    return {
        "app": "StockMind AI",
        "version": "1.0.0",
        "description": "Real-time stock intelligence platform",
        "docs": "/docs",
        "health": "/health",
        "disclaimer": (
            "This is an analytical decision-support system. "
            "Predictions are probabilistic estimates, not certainties. "
            "No trades are placed automatically."
        ),
    }
