from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied


class TeamNotFound(NotFound):
    default_detail = "Team not found."
    default_code = "team_not_found"


class InvitationNotFound(NotFound):
    default_detail = "Invitation not found."
    default_code = "invitation_not_found"


class MembershipNotFound(NotFound):
    default_detail = "Membership not found."
    default_code = "membership_not_found"


class TeamNotApproved(PermissionDenied):
    default_detail = "This team is awaiting superuser approval."
    default_code = "team_not_approved"


class NotTeamMember(PermissionDenied):
    default_detail = "You are not an approved member of this team."
    default_code = "not_team_member"


class RoleDomainMismatch(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "That role does not belong to this team's domain."
    default_code = "role_domain_mismatch"


class DuplicateMembership(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "That user is already a member of this team."
    default_code = "duplicate_membership"


class DuplicateInvitation(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A live invitation for that email and role already exists."
    default_code = "duplicate_invitation"


class InvitationNotAcceptable(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This invitation is not awaiting acceptance."
    default_code = "invitation_not_acceptable"


class InvitationExpired(APIException):
    status_code = status.HTTP_410_GONE
    default_detail = "This invitation has expired."
    default_code = "invitation_expired"


class InvitationEmailMismatch(PermissionDenied):
    default_detail = "This invitation was issued to a different email address."
    default_code = "invitation_email_mismatch"


class AlreadyReviewed(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This request has already been reviewed."
    default_code = "already_reviewed"
