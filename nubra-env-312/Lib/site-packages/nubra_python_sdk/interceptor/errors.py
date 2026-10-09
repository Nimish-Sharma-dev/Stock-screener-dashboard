#src/nubra_python_sdk/interceptor/errors.py
from pydantic import ValidationError # type: ignore

class NubraHttpError(Exception):
    """Base class for HTTP errors."""
    def __init__(self, message, status_code=None, response=None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class UnauthorizedError(NubraHttpError):
    """Raised when user is unauthorized (401) and 440."""
    pass


class BadRequestError(NubraHttpError):
    """Raised on 400-level client errors."""
    pass


class ServerError(NubraHttpError):
    """Raised on 500-level server errors."""
    pass


class RetryLimitExceeded(NubraHttpError):
    """Raised when max retry attempts are reached."""
    pass



class NubraValidationError(Exception):
    def __init__(self, validation_error: ValidationError):
        self.validation_error = validation_error
        super().__init__(str(validation_error))
