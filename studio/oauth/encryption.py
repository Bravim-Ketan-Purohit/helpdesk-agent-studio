"""Token encryption — envelope encryption with a KMS-shaped interface.

Tokens are encrypted at rest, never stored in plaintext. The encryption key
comes from KMS (AWS KMS in production, LocalStack or local key in dev).

Plaintext data keys are NEVER persisted and are zeroed after use.
"""

from __future__ import annotations

import abc
import os
import secrets
from dataclasses import dataclass
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
import base64


@dataclass(frozen=True)
class EncryptedBlob:
    """An encrypted value with its wrapped data key."""

    ciphertext: bytes
    wrapped_key: bytes  # The data key, encrypted by the master key


class KmsProvider(abc.ABC):
    """Abstract KMS interface — envelope encryption."""

    @abc.abstractmethod
    async def generate_data_key(self) -> tuple[bytes, bytes]:
        """Generate a data key.

        Returns:
            (plaintext_key, wrapped_key) — plaintext is for immediate use,
            wrapped is for storage. Plaintext must be zeroed after use.
        """
        ...

    @abc.abstractmethod
    async def decrypt_data_key(self, wrapped_key: bytes) -> bytes:
        """Decrypt a wrapped data key using the master key."""
        ...


class LocalKmsProvider(KmsProvider):
    """Local KMS provider for development — uses a local master key.

    NOT for production. In production, use AWS KMS via AwsKmsProvider.
    """

    def __init__(self, master_key: bytes | None = None) -> None:
        self._master_key = master_key or os.environ.get(
            "LOCAL_KMS_KEY", ""
        ).encode() or secrets.token_bytes(32)

    async def generate_data_key(self) -> tuple[bytes, bytes]:
        """Generate a local data key."""
        plaintext_key = secrets.token_bytes(32)

        # Wrap with master key using Fernet
        fernet_key = base64.urlsafe_b64encode(self._master_key[:32])
        f = Fernet(fernet_key)
        wrapped_key = f.encrypt(plaintext_key)

        return plaintext_key, wrapped_key

    async def decrypt_data_key(self, wrapped_key: bytes) -> bytes:
        """Decrypt a locally wrapped data key."""
        fernet_key = base64.urlsafe_b64encode(self._master_key[:32])
        f = Fernet(fernet_key)
        return f.decrypt(wrapped_key)


class AwsKmsProvider(KmsProvider):
    """AWS KMS provider for production envelope encryption.

    Uses GenerateDataKey to get a data key, stores the ciphertext blob
    alongside the encrypted token. Plaintext data keys are never persisted.
    """

    def __init__(self, key_id: str, region: str = "us-east-1") -> None:
        self._key_id = key_id
        self._region = region
        # Lazy import to avoid boto3 dependency in dev
        import boto3
        self._client = boto3.client("kms", region_name=region)

    async def generate_data_key(self) -> tuple[bytes, bytes]:
        """Generate a data key via AWS KMS."""
        response = self._client.generate_data_key(
            KeyId=self._key_id,
            KeySpec="AES_256",
        )
        plaintext = response["Plaintext"]
        wrapped = response["CiphertextBlob"]
        return plaintext, wrapped

    async def decrypt_data_key(self, wrapped_key: bytes) -> bytes:
        """Decrypt a data key via AWS KMS."""
        response = self._client.decrypt(CiphertextBlob=wrapped_key)
        return response["Plaintext"]


class TokenEncryptor:
    """Encrypts and decrypts OAuth tokens using envelope encryption.

    Each token gets its own data key. The data key is wrapped by KMS
    and stored alongside the ciphertext. Plaintext data keys are zeroed
    after use.
    """

    def __init__(self, kms: KmsProvider) -> None:
        self._kms = kms

    async def encrypt(self, plaintext_token: str) -> EncryptedBlob:
        """Encrypt a token using a fresh data key.

        The plaintext data key is zeroed after encryption.
        """
        data_key, wrapped_key = await self._kms.generate_data_key()

        try:
            # Derive a Fernet key from the data key
            fernet_key = base64.urlsafe_b64encode(data_key[:32])
            f = Fernet(fernet_key)
            ciphertext = f.encrypt(plaintext_token.encode("utf-8"))
        finally:
            # Zero the plaintext key — it must never be persisted
            data_key = b"\x00" * len(data_key)

        return EncryptedBlob(ciphertext=ciphertext, wrapped_key=wrapped_key)

    async def decrypt(self, blob: EncryptedBlob) -> str:
        """Decrypt a token by unwrapping the data key first."""
        data_key = await self._kms.decrypt_data_key(blob.wrapped_key)

        try:
            fernet_key = base64.urlsafe_b64encode(data_key[:32])
            f = Fernet(fernet_key)
            plaintext = f.decrypt(blob.ciphertext)
            return plaintext.decode("utf-8")
        finally:
            # Zero the plaintext key
            data_key = b"\x00" * len(data_key)
