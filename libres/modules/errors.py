class LibresError(Exception):
    pass


class ModifiedReadOnlySession(LibresError):
    pass


class DirtyReadOnlySession(LibresError):
    pass


class ContextAlreadyExists(LibresError):
    pass


class UnknownContext(LibresError):
    pass


class ContextIsLocked(LibresError):
    pass


class UnknownService(LibresError):
    pass


class UnknownUtility(LibresError):
    pass
