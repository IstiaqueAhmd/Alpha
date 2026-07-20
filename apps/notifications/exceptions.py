from rest_framework.exceptions import NotFound


class NotificationNotFound(NotFound):
    default_detail = "Notification not found."
    default_code = "notification_not_found"
