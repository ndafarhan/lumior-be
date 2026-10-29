"""Current time as a dependency, so tests can move it."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request

Clock = Callable[[], datetime]
"""Returns the current time as an aware UTC datetime."""


def system_clock() -> datetime:
    return datetime.now(UTC)


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


ClockDep = Annotated[Clock, Depends(get_clock)]
