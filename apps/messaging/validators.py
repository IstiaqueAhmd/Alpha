"""Upload validation for message attachments.

Plain allowlist (declared content_type + extension + size) rather than
sniffing file bytes - attachments are stored as-is, not re-encoded like
Pillow does for images elsewhere in this repo, so this is good enough to
reject the obviously wrong thing without a new native dependency.
"""

from rest_framework.exceptions import ValidationError

IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

DOCUMENT_CONTENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    "application/zip",
}
DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".zip",
}
DOCUMENT_MAX_BYTES = 25 * 1024 * 1024  # 25 MB

MAX_FILES_PER_MESSAGE = 10


def validate_attachment(upload) -> None:
    """Raise ValidationError if `upload` (a Django UploadedFile) isn't an
    allowed image or document. Callers decide `is_image` from this too.
    """
    content_type = (getattr(upload, "content_type", "") or "").lower()
    name = getattr(upload, "name", "") or ""
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    size = getattr(upload, "size", 0) or 0

    if content_type in IMAGE_CONTENT_TYPES:
        if size > IMAGE_MAX_BYTES:
            raise ValidationError(f"Image '{name}' exceeds the {IMAGE_MAX_BYTES // (1024 * 1024)}MB limit.")
        return

    if content_type in DOCUMENT_CONTENT_TYPES and ext in DOCUMENT_EXTENSIONS:
        if size > DOCUMENT_MAX_BYTES:
            raise ValidationError(f"File '{name}' exceeds the {DOCUMENT_MAX_BYTES // (1024 * 1024)}MB limit.")
        return

    raise ValidationError(f"'{name}' is not an allowed file type.")


def is_image(upload) -> bool:
    return (getattr(upload, "content_type", "") or "").lower() in IMAGE_CONTENT_TYPES
