"""Controlled errors raised at the Harness boundary."""


class ToolError(Exception):
    """Base class for errors that should be returned to the model."""


class ToolValidationError(ToolError):
    """Raised when a model-generated tool request is invalid or unsafe."""


class ModelError(Exception):
    """Base class for controlled model-client failures."""


class ModelConfigurationError(ModelError):
    """Raised when required local model configuration is missing."""


class ModelAPIError(ModelError):
    """Raised when the remote API cannot produce a usable response."""


class ModelResponseError(ModelError):
    """Raised when a successful HTTP response violates the expected protocol."""


class AgentError(Exception):
    """Base class for controlled execution-loop failures."""


class AgentLimitError(AgentError):
    """Raised when the model does not finish within the configured rounds."""
