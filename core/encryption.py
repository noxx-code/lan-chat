"""
core/encryption.py
──────────────────
Optional lightweight obfuscation / encryption layer.

The default implementation uses a repeating-XOR cipher with a fixed
app-level key.  This is NOT cryptographically secure – it prevents casual
sniffing but not a determined attacker.  For production use, swap in the
Fernet backend (requires `pip install cryptography`) or implement TLS.

Usage
─────
    from core.encryption import get_cipher

    cipher = get_cipher()          # or get_cipher("my-passphrase")
    ciphertext = cipher.encrypt(plaintext_bytes)
    plaintext  = cipher.decrypt(ciphertext)

To disable encryption entirely:
    cipher = NullCipher()

To integrate with the network layer, wrap Packet.to_json() / from_json()
calls through encrypt() / decrypt().  The current codebase does NOT enable
encryption by default to keep setup simple, but the interface is here and
ready to plug in.
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod


# ── Abstract interface ─────────────────────────────────────────────────────────

class Cipher(ABC):
    """Common interface for all cipher implementations."""

    @abstractmethod
    def encrypt(self, data: bytes) -> bytes: ...

    @abstractmethod
    def decrypt(self, data: bytes) -> bytes: ...


# ── Null cipher (no-op) ────────────────────────────────────────────────────────

class NullCipher(Cipher):
    """Pass-through cipher – disables encryption entirely."""

    def encrypt(self, data: bytes) -> bytes:
        return data

    def decrypt(self, data: bytes) -> bytes:
        return data


# ── XOR cipher ────────────────────────────────────────────────────────────────

_DEFAULT_PASSPHRASE = "LanChat-2024-SharedSecret"


class XorCipher(Cipher):
    """
    Repeating-XOR cipher.

    The key is derived from the passphrase using SHA-256 to produce a
    32-byte key regardless of passphrase length.  Because XOR is its own
    inverse, encrypt() and decrypt() are the same operation.

    Security note: XOR with a static key is breakable with known-plaintext
    attacks.  Use only as basic obfuscation on a trusted LAN.
    """

    def __init__(self, passphrase: str = _DEFAULT_PASSPHRASE) -> None:
        self._key = hashlib.sha256(passphrase.encode()).digest()  # 32 bytes

    def _xor(self, data: bytes) -> bytes:
        key = self._key
        key_len = len(key)
        return bytes(b ^ key[i % key_len] for i, b in enumerate(data))

    def encrypt(self, data: bytes) -> bytes:
        return self._xor(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._xor(data)  # XOR is self-inverse


# ── Fernet cipher (strong, optional) ──────────────────────────────────────────

class FernetCipher(Cipher):
    """
    AES-128-CBC + HMAC-SHA256 encryption via the `cryptography` package.

    Install: pip install cryptography

    A key is derived from the passphrase using PBKDF2-HMAC-SHA256 and a
    fixed salt (or supply your own).  This provides real confidentiality
    and integrity, unlike XorCipher.
    """

    def __init__(
        self,
        passphrase: str = _DEFAULT_PASSPHRASE,
        salt: bytes | None = None,
    ) -> None:
        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.primitives import hashes
            import base64
        except ImportError as exc:
            raise ImportError(
                "Install the 'cryptography' package to use FernetCipher: "
                "pip install cryptography"
            ) from exc

        _salt = salt or b"LanChat-Salt-2024"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_salt,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
        self._fernet = Fernet(key)

    def encrypt(self, data: bytes) -> bytes:
        return self._fernet.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._fernet.decrypt(data)


# ── Factory ────────────────────────────────────────────────────────────────────

def get_cipher(passphrase: str | None = None, backend: str = "null") -> Cipher:
    """
    Return a cipher instance.

    Parameters
    ----------
    passphrase : str | None
        Passphrase for keyed ciphers.  Ignored by NullCipher.
    backend : str
        One of "null" (default, no encryption), "xor", or "fernet".
    """
    if backend == "xor":
        return XorCipher(passphrase or _DEFAULT_PASSPHRASE)
    if backend == "fernet":
        return FernetCipher(passphrase or _DEFAULT_PASSPHRASE)
    return NullCipher()
