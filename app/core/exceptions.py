class AppError(Exception):
    """Base class for all application (domain) errors."""

    status_code: int = 500
    default_message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    default_message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    default_message = "The request conflicts with existing data."


class BadRequestError(AppError):
    status_code = 400
    default_message = "The request could not be processed."


class UnauthorizedError(AppError):
    status_code = 401
    default_message = "Authentication is required or credentials are invalid."


class ForbiddenError(AppError):
    status_code = 403
    default_message = "You do not have permission to perform this action."


class DatabaseConnectionError(AppError):
    status_code = 503
    default_message = "Could not connect to the database."


class DependencyExistsError(AppError):
    """
    Raised when attempting to delete a row that is still referenced by
    dependent rows in another table (parent/child integrity rule).
    """

    status_code = 409
    default_message = "This record cannot be deleted because it is referenced by other data."


class ValidationError(AppError):
    status_code = 422
    default_message = "The submitted data is invalid."


class RateLimitExceededError(AppError):
    status_code = 429
    default_message = "Too many requests. Please try again later."