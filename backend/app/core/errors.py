"""
Custom error classes and error handling.
"""


class APIError(Exception):
    """Base API error class."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AuthenticationError(APIError):
    """Authentication error."""
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, status_code=401)


class AuthorizationError(APIError):
    """Authorization error."""
    def __init__(self, message: str = "Not authorized"):
        super().__init__(message, status_code=403)


class NotFoundError(APIError):
    """Resource not found error."""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)
