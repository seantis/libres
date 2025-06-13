from __future__ import annotations

from libres.db.models.types.uuid_type import SoftUUID
from uuid import uuid4


def test_string_equal_uuid() -> None:
    uuid = uuid4()

    assert uuid == SoftUUID(uuid.hex)
    assert uuid.hex == SoftUUID(uuid.hex)
    assert str(uuid) == SoftUUID(uuid.hex)


def test_hashable_uuid() -> None:
    uuid = uuid4()

    assert hash(SoftUUID(uuid.hex))
