"""Opaque list cursors: the sort key `(spent_on, created_at, id)` of the last item returned.

Not signed: a cursor only selects a position in the caller's own household and month."""

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime


class InvalidCursorError(ValueError):
    pass


@dataclass(frozen=True)
class Cursor:
    spent_on: date
    created_at: datetime
    id: uuid.UUID


def encode_cursor(cursor: Cursor) -> str:
    payload = json.dumps(
        [cursor.spent_on.isoformat(), cursor.created_at.isoformat(), str(cursor.id)],
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(value: str) -> Cursor:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        spent_on, created_at, id_ = json.loads(raw)
        parsed = Cursor(
            date.fromisoformat(spent_on), datetime.fromisoformat(created_at), uuid.UUID(id_)
        )
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError) as exc:
        raise InvalidCursorError(str(exc)) from exc
    if parsed.created_at.tzinfo is None:
        raise InvalidCursorError("created_at must have a time zone")
    return parsed
