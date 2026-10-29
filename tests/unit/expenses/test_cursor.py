import base64
import uuid
from datetime import UTC, date, datetime

import pytest

from lumior.modules.expenses.cursor import (
    Cursor,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_round_trip_is_url_safe() -> None:
    cursor = Cursor(date(2026, 10, 3), datetime(2026, 10, 3, 8, 15, 0, 123456, UTC), uuid.uuid4())

    encoded = encode_cursor(cursor)

    assert decode_cursor(encoded) == cursor
    assert set(encoded) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


@pytest.mark.parametrize(
    "value",
    [
        "not-a-cursor",
        "",
        "%%%",
        b64("{}"),
        b64("[1, 2]"),
        b64('["2026-10-03", "2026-10-03T08:15:00+00:00"]'),
        b64('["2026-13-03", "2026-10-03T08:15:00+00:00", "' + str(uuid.uuid4()) + '"]'),
        b64('["2026-10-03", "yesterday", "' + str(uuid.uuid4()) + '"]'),
        b64('["2026-10-03", "2026-10-03T08:15:00+00:00", "not-a-uuid"]'),
        b64('["2026-10-03", "2026-10-03T08:15:00", "' + str(uuid.uuid4()) + '"]'),
        b64("[1, 2, 3]"),
    ],
)
def test_invalid_cursors(value: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(value)
