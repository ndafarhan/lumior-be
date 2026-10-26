"""Liveness and readiness probes, served outside the versioned API path."""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

READINESS_TIMEOUT_SECONDS = 2.0

CheckStatus = Literal["ok", "unavailable"]

router = APIRouter(prefix="/health", include_in_schema=False)


class LiveResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyChecks(BaseModel):
    database: CheckStatus


class ReadyResponse(BaseModel):
    status: CheckStatus
    checks: ReadyChecks


@router.get("/live")
async def live() -> LiveResponse:
    return LiveResponse()


async def check_database(engine: AsyncEngine, limit_seconds: float) -> CheckStatus:
    try:
        async with asyncio.timeout(limit_seconds), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        # Details go to the log only; the response must not reveal them.
        logger.warning("Readiness database check failed", exc_info=True)
        return "unavailable"
    return "ok"


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    database = await check_database(request.app.state.engine, READINESS_TIMEOUT_SECONDS)
    status: CheckStatus = "ok" if database == "ok" else "unavailable"
    body = ReadyResponse(status=status, checks=ReadyChecks(database=database))
    return JSONResponse(body.model_dump(), status_code=200 if status == "ok" else 503)
