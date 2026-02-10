from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import registry
from sqlalchemy.orm import DeclarativeBase
from uuid import UUID as PythonUUID

from .types import JSON
from .types import UTCDateTime
from .types import UUID


from typing import Any


class ORMBase(DeclarativeBase):

    registry = registry(type_annotation_map={
        datetime: UTCDateTime(timezone=False),
        dict[str, Any]: JSON,
        PythonUUID: UUID,
    })
