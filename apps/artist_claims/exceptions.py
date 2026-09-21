from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied


class ClaimNotFound(NotFound):
    default_detail = "Claim not found."
    default_code = "claim_not_found"


class NotYourClaim(PermissionDenied):
    default_detail = "This claim does not belong to you."
    default_code = "not_your_claim"


class ArtistTargetNotFound(NotFound):
    default_detail = "Artist not found."
    default_code = "artist_target_not_found"


class DuplicateClaim(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "You already have a live claim on this artist."
    default_code = "duplicate_claim"


class AlreadyReviewed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This claim has already been reviewed."
    default_code = "already_reviewed"
