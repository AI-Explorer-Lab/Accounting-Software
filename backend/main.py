from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.config import settings, validate_settings
from constant.values import API_PREFIX, APP_NAME, APP_VERSION
from controller.health_api import router as health_router
from controller.scaffold_api import router as scaffold_router
from controller.transaction_api import router as transaction_router
from database.lifecycle import close_database, create_tables, init_database
from exceptions.exception_handler import register_exception_handlers
from middlewares.auth_handler import register_auth_handlers
from middlewares.request_logging import RequestLoggingMiddleware


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    validate_settings()
    await init_database()
    await create_tables()
    try:
        yield
    finally:
        await close_database()


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    debug=bool(settings.environment.debug),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8101", "http://127.0.0.1:8101"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)
register_exception_handlers(app)
register_auth_handlers(app)
app.include_router(health_router, prefix=API_PREFIX)
app.include_router(scaffold_router, prefix=API_PREFIX)
app.include_router(transaction_router, prefix="/api")
