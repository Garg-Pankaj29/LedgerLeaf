"""Storage service for handling document files, validation, and SHA-256 hashing."""

import hashlib
import uuid
from pathlib import Path
from typing import Tuple
from backend.app.config import get_settings


class StorageError(Exception):
    """Base exception for storage and validation errors."""
    pass


class FileSizeLimitExceededError(StorageError):
    """Raised when uploaded file exceeds allowed size."""
    pass


class UnsupportedFileTypeError(StorageError):
    """Raised when file extension or MIME type is not allowed."""
    pass


class InvalidFileSignatureError(StorageError):
    """Raised when file content header does not match expected signature."""
    pass


ALLOWED_MIME_TYPES = {
    "application/pdf": [".pdf"],
    "image/png": [".png"],
    "image/jpeg": [".jpg", ".jpeg"],
    "image/webp": [".webp"],
    "text/plain": [".txt"],
}

# Magic signatures
FILE_SIGNATURES = {
    ".pdf": [b"%PDF-"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".webp": [b"RIFF"],  # also checks WEBP at byte offset 8
}


class StorageService:
    """Manages file validation, storage, signature checks, and retrieval in private directory."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def get_upload_dir(self) -> Path:
        """Return and ensure upload directory exists."""
        self.settings.ensure_directories()
        return self.settings.upload_dir

    def compute_sha256(self, content: bytes) -> str:
        """Compute SHA-256 hexadecimal digest of raw content."""
        hasher = hashlib.sha256()
        hasher.update(content)
        return hasher.hexdigest()

    def validate_file(self, original_filename: str, content_type: str, content: bytes) -> None:
        """
        Validate file extension, size limit, MIME type, and magic bytes signature.
        Raises descriptive StorageError subclasses on failure.
        """
        # 1. Size check
        file_size = len(content)
        if file_size == 0:
            raise StorageError("Uploaded file is empty (0 bytes).")
        if file_size > self.settings.max_upload_bytes:
            raise FileSizeLimitExceededError(
                f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds maximum allowed limit "
                f"of {self.settings.max_upload_mb} MB."
            )

        # 2. Extension check
        extension = Path(original_filename).suffix.lower()
        if not extension or extension not in self.settings.allowed_extensions:
            allowed = ", ".join(self.settings.allowed_extensions)
            raise UnsupportedFileTypeError(
                f"File extension '{extension}' is not supported. Allowed extensions: {allowed}"
            )

        # 3. MIME type check
        normalized_mime = content_type.lower().split(";")[0].strip()
        if normalized_mime not in ALLOWED_MIME_TYPES:
            # If browser sends generic octet-stream, check extension validity
            if normalized_mime != "application/octet-stream":
                raise UnsupportedFileTypeError(
                    f"MIME type '{content_type}' is not supported. "
                    f"Allowed MIME types: {', '.join(ALLOWED_MIME_TYPES.keys())}"
                )

        # 4. File signature (magic bytes) verification
        if extension in FILE_SIGNATURES:
            signatures = FILE_SIGNATURES[extension]
            matched = any(content.startswith(sig) for sig in signatures)
            if extension == ".webp" and matched:
                # WEBP has "RIFF" at 0..4 and "WEBP" at 8..12
                matched = len(content) >= 12 and content[8:12] == b"WEBP"

            if not matched:
                raise InvalidFileSignatureError(
                    f"File signature does not match expected format for '{extension}'. "
                    "The file appears to be corrupted or mislabeled."
                )
        elif extension == ".txt":
            # Verify plain text doesn't contain suspicious binary null bytes
            if b"\x00" in content[:1024]:
                raise InvalidFileSignatureError(
                    "File content contains binary null bytes and is not valid text."
                )

    def save_file(self, content: bytes, original_filename: str, content_type: str = "") -> Tuple[str, str, int]:
        """
        Validate and save file to secure storage directory with a unique UUID-based filename.
        Returns:
            Tuple of (stored_filename, sha256_hash, file_size)
        """
        if content_type:
            self.validate_file(original_filename, content_type, content)

        upload_dir = self.get_upload_dir()
        extension = Path(original_filename).suffix.lower()
        unique_name = f"{uuid.uuid4().hex}{extension}"
        target_path = upload_dir / unique_name

        target_path.write_bytes(content)

        file_size = len(content)
        sha256_hash = self.compute_sha256(content)

        return unique_name, sha256_hash, file_size

    def get_file_path(self, stored_filename: str) -> Path:
        """
        Resolve absolute path to a stored file, strictly enforcing that the file
        resides within the private upload directory to prevent path traversal attacks.
        """
        upload_dir = self.get_upload_dir().resolve()
        safe_name = Path(stored_filename).name
        if not safe_name or safe_name != stored_filename:
            raise StorageError(f"Access denied: path traversal detected in filename '{stored_filename}'.")

        target = (upload_dir / safe_name).resolve()
        try:
            target.relative_to(upload_dir)
        except ValueError:
            raise StorageError(f"Access denied: path traversal detected in filename '{stored_filename}'.")

        return target

    def delete_file(self, stored_filename: str) -> bool:
        """Safely delete stored file from disk."""
        target_path = self.get_file_path(stored_filename)
        if target_path.exists() and target_path.is_file():
            target_path.unlink()
            return True
        return False
