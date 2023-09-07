from __future__ import annotations


class TiliaException(Exception):
    pass


class TiliaExit(TiliaException):
    pass


class UserCancelledDialog(TiliaException):
    pass


class CreateComponentError(TiliaException):
    pass


class InvalidComponentKindError(TiliaException):
    pass


class NoReplyToRequest(TiliaException):
    """Raised when to call a request, but there is no callback attached to it"""

    pass


class NoCallbackAttached(TiliaException):
    """Raised when a request callback is not found"""

    pass


class TimelineUINotFound(TiliaException):
    """Raised when a timeline UI is not found when trying to get it by id"""

    pass


class TiliaFileWriteError(TiliaException):
    pass


class MediaMetadataFieldNotFound(TiliaException):
    pass


class TimelineValidationError(TiliaException):
    pass


class WrongTimelineForImport(TiliaException):
    pass


class SetComponentDataError(TiliaException):
    pass


class GetComponentDataError(TiliaException):
    pass


class SetTimelineDataError(TiliaException):
    pass


class GetTimelineDataError(TiliaException):
    pass
