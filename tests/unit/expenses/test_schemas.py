import uuid

import pytest
from pydantic import ValidationError as PydanticValidationError

from lumior.modules.expenses.schemas import CreateExpenseRequest, UpdateExpenseRequest

BODY = {
    "amount": {"amount": "45000.00", "currency": "IDR"},
    "spent_on": "2026-10-03",
    "category_id": str(uuid.uuid4()),
}


@pytest.mark.parametrize(
    ("note", "stored"),
    [(" Weekly market ", "Weekly market"), ("   ", None), ("", None), (None, None)],
)
def test_note_is_trimmed_and_empty_becomes_null(note: str | None, stored: str | None) -> None:
    assert CreateExpenseRequest.model_validate({**BODY, "note": note}).note == stored


def test_note_limit_counts_after_trimming() -> None:
    assert CreateExpenseRequest.model_validate({**BODY, "note": f" {'n' * 500} "}).note == "n" * 500
    with pytest.raises(PydanticValidationError) as excinfo:
        CreateExpenseRequest.model_validate({**BODY, "note": "n" * 501})
    assert [e["loc"] for e in excinfo.value.errors()] == [("note",)]


def test_update_tells_omitted_note_from_null() -> None:
    omitted = UpdateExpenseRequest.model_validate({"spent_on": "2026-10-04"})
    cleared = UpdateExpenseRequest.model_validate({"note": None})

    assert "note" not in omitted.model_fields_set
    assert "note" in cleared.model_fields_set
    assert cleared.note is None


@pytest.mark.parametrize("field", ["amount", "spent_on", "category_id"])
def test_update_rejects_null_for_required_fields(field: str) -> None:
    with pytest.raises(PydanticValidationError) as excinfo:
        UpdateExpenseRequest.model_validate({field: None})
    assert [e["loc"] for e in excinfo.value.errors()] == [(field,)]


def test_empty_update_is_valid() -> None:
    assert UpdateExpenseRequest.model_validate({}).model_fields_set == set()
