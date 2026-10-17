"""Text extraction service supporting text-based PDFs, images with OCR, and plain text files."""

import io
from pathlib import Path
from typing import Tuple
from PIL import Image
from pypdf import PdfReader


class TextExtractionError(Exception):
    """Base exception for text extraction failures."""
    pass


class UnsupportedFileFormatError(TextExtractionError):
    """Raised when file format cannot be parsed for text."""
    pass


class EmptyTextError(TextExtractionError):
    """Raised when extraction produces no legible text."""
    pass


class OCRError(TextExtractionError):
    """Raised when OCR engine encounters an error or is missing."""
    pass


class TextExtractionService:
    """Extracts raw text from documents (PDFs, images, and text files)."""

    def extract_text(self, file_path: Path, mime_type: str = "") -> Tuple[str, str]:
        """
        Extract text from file based on extension and MIME type.
        Returns:
            Tuple of (extracted_text, extraction_method)
        Raises:
            TextExtractionError subclasses with understandable error messages.
        """
        if not file_path.exists():
            raise TextExtractionError(f"File not found: {file_path}")

        ext = file_path.suffix.lower()

        if ext == ".pdf":
            return self._extract_from_pdf(file_path)
        elif ext in (".png", ".jpg", ".jpeg", ".webp"):
            return self._extract_from_image(file_path)
        elif ext == ".txt":
            return self._extract_from_txt(file_path)
        else:
            raise UnsupportedFileFormatError(
                f"Unsupported file format '{ext}' for text extraction. Supported formats: .pdf, .png, .jpg, .jpeg, .webp, .txt"
            )

    def _extract_from_pdf(self, file_path: Path) -> Tuple[str, str]:
        """Extract text from PDF pages using pypdf, falling back to OCR if scanned."""
        try:
            reader = PdfReader(str(file_path))
            pages_text = []

            for page in reader.pages:
                text = page.extract_text() or ""
                if text.strip():
                    pages_text.append(text.strip())

            full_text = "\n\n".join(pages_text).strip()

            if full_text:
                return full_text, "pdf_text"

            # If no embedded text layer was found, attempt OCR on embedded page images
            return self._ocr_pdf_images(reader, file_path)

        except TextExtractionError:
            raise
        except Exception as exc:
            raise TextExtractionError(f"Failed to read PDF file '{file_path.name}': {exc}")

    def _ocr_pdf_images(self, reader: PdfReader, file_path: Path) -> Tuple[str, str]:
        """Extract images from PDF pages and apply OCR."""
        try:
            import pytesseract
        except ImportError:
            raise OCRError(
                "PDF contains no embedded text layer, and pytesseract is not available for OCR."
            )

        ocr_texts = []
        for page_idx, page in enumerate(reader.pages):
            for image_file_object in page.images:
                try:
                    img = Image.open(io.BytesIO(image_file_object.data))
                    text = pytesseract.image_to_string(img)
                    if text.strip():
                        ocr_texts.append(text.strip())
                except pytesseract.TesseractNotFoundError:
                    raise OCRError(
                        "PDF contains scanned images, but Tesseract OCR is not installed on this system. "
                        "Install tesseract-ocr to enable scanned document processing."
                    )
                except Exception as exc:
                    # Continue attempting other images
                    continue

        full_text = "\n\n".join(ocr_texts).strip()
        if not full_text:
            raise EmptyTextError(
                f"PDF '{file_path.name}' contains no extractable text layer or legible scanned text."
            )
        return full_text, "pdf_ocr"

    def _extract_from_image(self, file_path: Path) -> Tuple[str, str]:
        """Extract text from an image file using local OCR."""
        try:
            import pytesseract
        except ImportError:
            raise OCRError("pytesseract library is required for image OCR.")

        try:
            with Image.open(file_path) as img:
                # Convert RGBA / P to RGB for OCR compatibility
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                text = pytesseract.image_to_string(img)
                cleaned = text.strip()
                if not cleaned:
                    raise EmptyTextError(
                        f"Image '{file_path.name}' processed via OCR, but no legible text was detected."
                    )
                return cleaned, "image_ocr"
        except pytesseract.TesseractNotFoundError:
            raise OCRError(
                "Local OCR engine (Tesseract) is not installed on this machine. "
                "Install tesseract-ocr (e.g. `sudo apt-get install tesseract-ocr`) to process image files."
            )
        except TextExtractionError:
            raise
        except Exception as exc:
            raise OCRError(f"OCR failure processing image '{file_path.name}': {exc}")

    def _extract_from_txt(self, file_path: Path) -> Tuple[str, str]:
        """Extract text from a plain text file."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = file_path.read_text(encoding="latin-1")
            except Exception as exc:
                raise TextExtractionError(f"Failed to decode text file '{file_path.name}': {exc}")

        cleaned = content.strip()
        if not cleaned:
            raise EmptyTextError(f"Document text file '{file_path.name}' is empty.")

        return cleaned, "plain_text"
