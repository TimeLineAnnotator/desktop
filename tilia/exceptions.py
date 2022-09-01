class AppException(Exception):
    pass


class UserCancelledSaveError(AppException):
    pass


class UserCancelledOpenError(AppException):
    pass
