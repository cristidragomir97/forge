"""
Custom exception hierarchy for forge.

Replaces sys.exit() calls with proper exceptions for better error handling and cleanup.
"""

class ForgeError(Exception):
    """Base exception for all forge errors."""
    def __init__(self, message: str, context: dict = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self):
        return self.message


class ConfigurationError(ForgeError):
    """Raised when configuration validation fails."""
    pass


class ValidationError(ForgeError):
    """Raised when validation checks fail."""
    pass


class WorkspaceError(ForgeError):
    """Raised when workspace operations fail."""
    pass


class SourceNotFoundError(ForgeError):
    """Raised when source paths don't exist."""
    pass


class DockerError(ForgeError):
    """Raised when Docker operations fail."""
    pass


class HostError(ForgeError):
    """Raised when host-related operations fail."""
    pass


class BuildError(ForgeError):
    """Raised when build operations fail."""
    pass


class DeployError(ForgeError):
    """Raised when deployment operations fail."""
    pass
