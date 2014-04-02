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


class InvalidAllocationError(LibresError):
    pass


class OverlappingAllocationError(LibresError):

    def __init__(self, start, end, existing):
        self.start = start
        self.end = end
        self.existing = existing


class DatesMayNotBeEqualError(LibresError):
    pass
