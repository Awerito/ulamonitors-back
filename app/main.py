from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import create_admin_user
from app.config import API_DESCRIPTION, API_TITLE, API_VERSION, settings
from app.database.indexes import ensure_indexes
from app.database.mongo import connect, disconnect
from app.scheduler.core import start_scheduler, stop_scheduler
from app.utils.logger import logger

from app.routers.healthcheck.endpoints import router as healthcheck_router
from app.routers.auth.endpoints import router as auth_router
from app.routers.sites.endpoints import router as sites_router
from app.routers.sensors.endpoints import router as sensors_router
from app.routers.measurements.endpoints import router as measurements_router
from app.routers.interventions.endpoints import router as interventions_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    """
    Lifespan context for application startup and shutdown.
    """
    if settings.env.startswith("dev"):
        logger.warning("Running in development mode!")

    db = await connect()
    await ensure_indexes(db)
    # Demo data is not created here: it comes from scripts/seed.py.
    await create_admin_user(db)

    # Start scheduler (opt-in via ENABLE_SCHEDULER)
    if settings.enable_scheduler:
        start_scheduler()

    yield  # Application is running

    if settings.enable_scheduler:
        stop_scheduler()

    # Close MongoDB connection
    await disconnect()


# Initialize FastAPI application
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    # The JWT travels in the Authorization header, and browsers reject
    # "*" together with credentials.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(healthcheck_router)
app.include_router(auth_router)
app.include_router(sites_router)
app.include_router(sensors_router)
app.include_router(measurements_router)
app.include_router(interventions_router)
