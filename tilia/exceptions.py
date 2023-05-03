class TiliaException(Exception):
    pass


class UserCancelledSaveError(TiliaException):
    pass


class UserCancelledOpenError(TiliaException):
    pass


class CreateComponentError(TiliaException):
    pass
