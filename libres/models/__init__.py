from sqlalchemy.ext import declarative
ORMBase = declarative.declarative_base()

from libres.models.allocation import Allocation
Allocation  # pyflakes
