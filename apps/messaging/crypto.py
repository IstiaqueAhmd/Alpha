from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.db import models


def _cipher() -> MultiFernet | None:
    """Built fresh per call (not cached at import/module scope) so
    `override_settings(MESSAGE_ENCRYPTION_KEYS=...)` in tests takes effect
    immediately. Fernet construction is cheap. Returns None when no key is
    configured, in which case the field is a plain passthrough - lets local
    dev run without MESSAGE_ENCRYPTION_KEYS set.
    """
    keys = settings.MESSAGE_ENCRYPTION_KEYS
    if not keys:
        return None
    return MultiFernet([Fernet(key.encode()) for key in keys])


class EncryptedTextField(models.TextField):
    """TextField that is encrypted at rest, transparent to callers.

    Encrypts with the first (active) key in MESSAGE_ENCRYPTION_KEYS on
    write; decrypts by trying every key in that list, in order, on read -
    which is what makes key rotation possible: a message written under an
    old key stays readable as long as that key is still listed, even after
    a new key has taken index 0 for new writes. A value that fails every
    key (row written before encryption was enabled, or no key configured)
    is returned as-is rather than raised, since InvalidToken there means
    "not our ciphertext", not "corrupted".
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value:
            return value
        cipher = _cipher()
        if cipher is None:
            return value
        return cipher.encrypt(value.encode()).decode()

    def from_db_value(self, value, expression, connection):
        if not value:
            return value
        cipher = _cipher()
        if cipher is None:
            return value
        try:
            return cipher.decrypt(value.encode()).decode()
        except InvalidToken:
            return value
