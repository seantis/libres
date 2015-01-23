from libres.db.models.types.guid import StringEqualUUID
from uuid import uuid4


def test_string_equal_uuid():
    uuid = uuid4()

    assert uuid == StringEqualUUID(uuid.hex)
    assert uuid.hex == StringEqualUUID(uuid.hex)
    assert str(uuid) == StringEqualUUID(uuid.hex)
