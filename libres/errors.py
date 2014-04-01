class LibresError(Exception):
    pass


class ModifiedReadOnlySession(LibresError):
    pass


class DirtyReadOnlySession(LibresError):
    pass
