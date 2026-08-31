"""Errors raised for expected, model-caused tool failures."""


class ToolError(Exception):
    """Base class for errors that should be returned to the model."""


class ToolValidationError(ToolError):
    """Raised when a model-generated tool request is invalid or unsafe."""

