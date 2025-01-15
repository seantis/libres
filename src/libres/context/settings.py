from __future__ import annotations

import textwrap
from uuid import UUID


from typing import Any
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from libres.context.core import Context


_default: dict[str, tuple[Any, str]] = {}

_default['settings.dsn'] = (
    None,
    """
    The data source name to connect to the right database. For example:
    postgresql+psycopg2://user:password@localhost:5432/database
    """
)

_default['settings.uuid_namespace'] = (
    UUID('49326ef9-fbc0-4ac0-9508-b0bbd75d42f7'),
    """
    The namespace used by the scheduler to create uuids out of the context
    and the name. You usually don't want to change this. You really do not
    want to change it once you have created records using the scheduler -
    otherwise you will lose the connection between your context/name and
    the specific record in the database.

    Just leave it really.
    """
)


def set_default_settings(context: Context) -> None:
    for name, (value, _) in _default.items():
        context.set(name, value)


doc = []


for name, (value, help_str) in _default.items():
    reference = f'.. _{name}:\n'
    title = '{name}\n{line}'.format(name=name, line='-' * len(name))
    default = f'default: **{value!r}**'
    help_str = textwrap.dedent(help_str)

    doc.append(f'{reference}\n{title}\n{default}\n{help_str}')

__doc__ = '\n'.join(doc)
