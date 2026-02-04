from __future__ import annotations


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sqlalchemy.ext.declarative import declarative_base
else:
    # FIXME: Move this import out when dropping 1.4 support
    from sqlalchemy.orm import declarative_base

ORMBase = declarative_base()
