from rest_framework.exceptions import APIException


class EmailNotVerified(APIException):
    status_code = 403
    default_detail = "Please verify your email before logging in."
    default_code = "email_not_verified"


class GoogleAccountNotFound(APIException):
    status_code = 404
    default_detail = "No account found for this Google identity. Please sign up first."
    default_code = "account_not_found"


class GoogleConfigError(APIException):
    status_code = 503
    default_detail = "Google sign-in is not configured."
    default_code = "google_not_configured"
