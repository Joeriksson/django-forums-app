"""Authenticator secrets and recovery-code seeds are encrypted in the database."""

import base64
import importlib
import os

import pytest
from allauth.mfa.models import Authenticator
from allauth.mfa.recovery_codes.internal.auth import RecoveryCodes
from allauth.mfa.totp.internal import auth as totp
from cryptography.fernet import InvalidToken
from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse

from users.encryption import PREFIX, decrypt_secret, encrypt_secret

User = get_user_model()

EMAIL = 'member@example.com'
PASSWORD = 'testpass123'


def totp_code(secret):
    """The code an authenticator app shows right now for `secret`."""
    counter = next(totp.yield_hotp_counters_from_time())
    return totp.format_hotp_value(totp.hotp_value(secret, counter))


def new_key():
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


@pytest.fixture
def user(db, verify_email):
    return verify_email(User.objects.create_user(username='member', email=EMAIL, password=PASSWORD))


def stored(user, type):
    return Authenticator.objects.get(user=user, type=type).data


def test_encrypt_and_decrypt_round_trip():
    encrypted = encrypt_secret('JBSWY3DPEHPK3PXP')

    assert encrypted.startswith(PREFIX)
    assert 'JBSWY3DPEHPK3PXP' not in encrypted
    assert decrypt_secret(encrypted) == 'JBSWY3DPEHPK3PXP'


def test_same_secret_encrypts_differently_each_time():
    assert encrypt_secret('secret') != encrypt_secret('secret')


def test_another_key_cannot_decrypt(settings):
    encrypted = encrypt_secret('secret')
    settings.MFA_ENCRYPTION_KEY = new_key()

    with pytest.raises(InvalidToken):
        decrypt_secret(encrypted)


def test_cleartext_is_refused():
    """No fallback: a value that isn't encrypted is an error, not a secret."""
    with pytest.raises(ValueError, match='not encrypted'):
        decrypt_secret('JBSWY3DPEHPK3PXP')


def test_totp_secret_is_not_readable_in_the_database(user, add_totp):
    secret = add_totp(user)

    data = stored(user, Authenticator.Type.TOTP)

    assert data['secret'].startswith(PREFIX)
    assert secret not in str(data)


def test_recovery_seed_is_not_readable_in_the_database(user):
    codes = RecoveryCodes.activate(user).get_unused_codes()

    data = stored(user, Authenticator.Type.RECOVERY_CODES)

    assert data['seed'].startswith(PREFIX)
    assert len(codes) > 0
    # The same codes come back from the stored, encrypted seed
    authenticator = Authenticator.objects.get(user=user, type=Authenticator.Type.RECOVERY_CODES)
    assert authenticator.wrap().get_unused_codes() == codes


def test_login_with_code_from_an_encrypted_secret(client, user, add_totp):
    secret = add_totp(user)

    client.post(reverse('account_login'), {'login': EMAIL, 'password': PASSWORD})
    client.post(reverse('mfa_authenticate'), {'code': totp_code(secret)})

    assert client.session['_auth_user_id'] == str(user.pk)


def test_login_with_recovery_code_from_an_encrypted_seed(client, user, add_totp):
    add_totp(user)
    code = RecoveryCodes.activate(user).get_unused_codes()[0]

    client.post(reverse('account_login'), {'login': EMAIL, 'password': PASSWORD})
    client.post(reverse('mfa_authenticate'), {'code': code})

    assert client.session['_auth_user_id'] == str(user.pk)


# Rows from before the encryption


@pytest.fixture
def migration():
    return importlib.import_module('users.migrations.0006_encrypt_mfa_secrets')


@pytest.fixture
def cleartext_rows(user):
    secret = totp.generate_totp_secret()
    seed = RecoveryCodes.generate_seed()
    Authenticator.objects.create(user=user, type=Authenticator.Type.TOTP, data={'secret': secret})
    Authenticator.objects.create(
        user=user,
        type=Authenticator.Type.RECOVERY_CODES,
        data={'seed': seed, 'used_mask': 3, 'migrated_codes': ['11111111', '22222222']},
    )
    return secret, seed


def test_migration_encrypts_cleartext_rows(user, cleartext_rows, migration):
    secret, seed = cleartext_rows

    migration.encrypt_rows(apps, None)

    totp_data = stored(user, Authenticator.Type.TOTP)
    recovery_data = stored(user, Authenticator.Type.RECOVERY_CODES)
    assert decrypt_secret(totp_data['secret']) == secret
    assert decrypt_secret(recovery_data['seed']) == seed
    assert [decrypt_secret(code) for code in recovery_data['migrated_codes']] == ['11111111', '22222222']
    # Everything else is left alone
    assert recovery_data['used_mask'] == 3
    assert secret not in str(totp_data) and seed not in str(recovery_data)


def test_migrated_authenticator_still_checks_codes(user, cleartext_rows, migration):
    secret, _ = cleartext_rows

    migration.encrypt_rows(apps, None)

    authenticator = Authenticator.objects.get(user=user, type=Authenticator.Type.TOTP)
    assert authenticator.wrap().validate_code(totp_code(secret))


def test_migration_leaves_encrypted_rows_alone(user, add_totp, migration):
    add_totp(user)
    before = stored(user, Authenticator.Type.TOTP)

    migration.encrypt_rows(apps, None)

    assert stored(user, Authenticator.Type.TOTP) == before


def test_migration_can_be_reversed(user, cleartext_rows, migration):
    secret, seed = cleartext_rows
    migration.encrypt_rows(apps, None)

    migration.decrypt_rows(apps, None)

    assert stored(user, Authenticator.Type.TOTP)['secret'] == secret
    assert stored(user, Authenticator.Type.RECOVERY_CODES)['seed'] == seed
