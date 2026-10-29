"""Aggregates all `/api/v1` routers. Modules register their routers here."""

from fastapi import APIRouter

from lumior.modules.households.router import households_router, invites_router
from lumior.modules.identity.router import auth_router, me_router

API_V1_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_V1_PREFIX)
api_router.include_router(auth_router)
api_router.include_router(me_router)
api_router.include_router(households_router)
api_router.include_router(invites_router)
