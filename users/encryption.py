"""
Encryption of the two-factor secrets allauth keeps in the database: the
authenticator app's secret and the seed of the recovery codes.

Whoever reads the database (a leaked backup, say) would otherwise get every
user's second factor along with the password hashes. The key is not in the
database: settings.MFA_ENCRYPTION_KEY, from DJANGO_MFA_ENCRYPTION_KEY.
"""

from cryptography.fernet import Fernet
from django.conf import settings

# Marks a stored value as encrypted, and with what
PREFIX = 'fernet:'


def _fernet():
    return Fernet(settings.MFA_ENCRYPTION_KEY)


def is_encrypted(stored):
    return stored.startswith(PREFIX)


def encrypt_secret(text):
    return PREFIX + _fernet().encrypt(text.encode()).decode()


def decrypt_secret(stored):
    """Raises InvalidToken if the value was encrypted with another key."""
    # No fallback to cleartext: what isn't encrypted is not accepted as a secret
    if not is_encrypted(stored):
        raise ValueError('The stored two-factor secret is not encrypted. Run migrate.')
    return _fernet().decrypt(stored[len(PREFIX):].encode()).decode()
