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


class InvalidEmailAddress(LibresError):
    pass


class ReservationTooLong(LibresError):
    pass


class ReservationTooShort(LibresError):
    pass


class ReservationParametersInvalid(LibresError):
    pass


class AlreadyReservedError(LibresError):
    pass


class QuotaOverLimit(LibresError):
    pass


class QuotaImpossible(LibresError):
    pass


class InvalidQuota(LibresError):
    pass


class InvalidReservationError(LibresError):
    pass


class NotReservableError(LibresError):
    pass


class NoReservationsToConfirm(LibresError):
    pass


class InvalidReservationToken(LibresError):
    pass


class OverlappingAllocationError(LibresError):

    def __init__(self, start, end, existing):
        self.start = start
        self.end = end
        self.existing = existing


class OverlappingReservationError(LibresError):
    pass


class AffectedReservationError(LibresError):

    def __init__(self, existing):
        self.existing = existing


class AffectedPendingReservationError(AffectedReservationError):
    pass


class DatesMayNotBeEqualError(LibresError):
    pass


class TimerangeTooLong(LibresError):
    pass


class NotTimezoneAware(LibresError):
    pass
