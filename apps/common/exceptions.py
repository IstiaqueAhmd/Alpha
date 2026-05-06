import logging

from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    """Wrap DRF errors in a consistent envelope.

    Successful responses follow ``{"success": true, ...}``; error responses use
    ``{"success": false, "error": {"code": ..., "status": ..., "message": ...,
    "details": ...}}`` so the frontend can route on ``error.code`` regardless
    of which view raised the exception.
    """
    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled exception in API view", exc_info=exc)
        return None

    code = getattr(exc, "default_code", "error")
    if isinstance(response.data, dict) and isinstance(response.data.get("code"), str):
        code = response.data["code"]

    response.data = {
        "success": False,
        "error": {
            "code": code,
            "status": response.status_code,
            "message": _extract_message(response.data),
            "details": response.data,
        },
    }
    return response


def _extract_message(data) -> str:
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        for value in data.values():
            extracted = _extract_message(value)
            if extracted:
                return extracted
        return "Validation error."
    if isinstance(data, list) and data:
        return _extract_message(data[0])
    if isinstance(data, str):
        return data
    return "Error."
