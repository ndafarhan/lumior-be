"""Aggregates all `/api/v1` routers. Modules register their routers here."""

from fastapi import APIRouter

API_V1_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_V1_PREFIX)
