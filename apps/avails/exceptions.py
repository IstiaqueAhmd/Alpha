from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied


class AvailListNotFound(NotFound):
    default_detail = "Avail list not found."
    default_code = "avail_list_not_found"


class AvailEntryNotFound(NotFound):
    default_detail = "Avail entry not found."
    default_code = "avail_entry_not_found"


class AvailShareNotFound(NotFound):
    default_detail = "Share record not found."
    default_code = "avail_share_not_found"


class AvailListAccessDenied(PermissionDenied):
    default_detail = "You do not have access to this avail list."
    default_code = "avail_list_access_denied"


class NotAvailListOwner(PermissionDenied):
    default_detail = "Only the list owner can perform this action."
    default_code = "not_avail_list_owner"


class DuplicateAvailEntry(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This artist is already in the list."
    default_code = "duplicate_avail_entry"


class DuplicateAvailShare(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This list is already shared with that user."
    default_code = "duplicate_avail_share"
