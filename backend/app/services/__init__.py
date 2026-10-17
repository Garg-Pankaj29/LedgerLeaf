"""Backend services package for storage, text extraction, validation, and local AI inference."""

from backend.app.services.storage_service import (
    StorageService,
    StorageError,
    FileSizeLimitExceededError,
    UnsupportedFileTypeError,
    InvalidFileSignatureError,
)
from backend.app.services.text_extraction_service import (
    TextExtractionService,
    TextExtractionError,
    UnsupportedFileFormatError,
    EmptyTextError,
    OCRError,
)
from backend.app.services.local_ai import (
    LocalAIService,
    LocalAIError,
    AIConnectionError,
    AITimeoutError,
    AIModelNotFoundError,
    AIResponseError,
    AIValidationError,
    AIStructuredOutput,
)
from backend.app.services.validation_service import ValidationService

__all__ = [
    "StorageService",
    "StorageError",
    "FileSizeLimitExceededError",
    "UnsupportedFileTypeError",
    "InvalidFileSignatureError",
    "TextExtractionService",
    "TextExtractionError",
    "UnsupportedFileFormatError",
    "EmptyTextError",
    "OCRError",
    "LocalAIService",
    "LocalAIError",
    "AIConnectionError",
    "AITimeoutError",
    "AIModelNotFoundError",
    "AIResponseError",
    "AIValidationError",
    "AIStructuredOutput",
    "ValidationService",
]
