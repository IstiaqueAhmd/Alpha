from rest_framework.throttling import AnonRateThrottle


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class RegisterThrottle(AnonRateThrottle):
    scope = "register"


class PasswordResetThrottle(AnonRateThrottle):
    scope = "password_reset"


class OTPVerifyThrottle(AnonRateThrottle):
    scope = "otp_verify"


class GoogleAuthThrottle(AnonRateThrottle):
    scope = "google_auth"
