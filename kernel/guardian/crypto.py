"""Cryptographic primitives for sovereign identity (Ed25519) and vault (AES-256-GCM)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode("ascii"))


@dataclass
class SovereignIdentity:
    identity_id: str
    public_key_b64: str
    fingerprint: str
    created_at: str


class CryptoEngine:
    """Manages local Ed25519 identity keys and AES-256-GCM vault encryption."""

    def __init__(self, guardian_dir: Path) -> None:
        self.guardian_dir = guardian_dir
        self.guardian_dir.mkdir(parents=True, exist_ok=True)
        self._priv_path = guardian_dir / "identity_ed25519.pem"
        self._meta_path = guardian_dir / "identity.json"
        self._vault_salt_path = guardian_dir / "vault.salt"
        self._vault_key_path = guardian_dir / "vault.local.key"
        self._private_key: Ed25519PrivateKey | None = None
        self._identity: SovereignIdentity | None = None
        self._aes_key: bytes | None = None
        self._ensure_identity()

    def _ensure_identity(self) -> None:
        if self._priv_path.exists() and self._meta_path.exists():
            raw = self._priv_path.read_bytes()
            self._private_key = serialization.load_pem_private_key(raw, password=None)
            meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
            self._identity = SovereignIdentity(**meta)
            return

        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key()
        pub_raw = pub.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        fingerprint = hashlib.sha256(pub_raw).hexdigest()[:16].upper()
        identity_id = f"did:newera:{fingerprint.lower()}"
        created_at = datetime.now(timezone.utc).isoformat()

        pem = priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        self._priv_path.write_bytes(pem)
        meta = {
            "identity_id": identity_id,
            "public_key_b64": _b64e(pub_raw),
            "fingerprint": fingerprint,
            "created_at": created_at,
        }
        self._meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        self._private_key = priv
        self._identity = SovereignIdentity(**meta)

    @property
    def identity(self) -> SovereignIdentity:
        assert self._identity is not None
        return self._identity

    def _ensure_vault_key(self, passphrase: str | None = None) -> bytes:
        if self._aes_key is not None and passphrase is None:
            return self._aes_key

        if passphrase:
            if self._vault_salt_path.exists():
                salt = self._vault_salt_path.read_bytes()
            else:
                salt = os.urandom(16)
                self._vault_salt_path.write_bytes(salt)
            kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
            self._aes_key = kdf.derive(passphrase.encode("utf-8"))
            return self._aes_key

        # Local device-sealed key so vault works seamlessly out-of-the-box
        if self._vault_key_path.exists():
            self._aes_key = _b64d(self._vault_key_path.read_text(encoding="ascii").strip())
        else:
            self._aes_key = AESGCM.generate_key(bit_length=256)
            self._vault_key_path.write_text(_b64e(self._aes_key), encoding="ascii")
        return self._aes_key

    def encrypt_secret(self, plaintext: str, aad: str = "") -> tuple[str, str]:
        """Encrypts plaintext using AES-256-GCM. Returns (nonce_b64, ciphertext_b64)."""
        key = self._ensure_vault_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))
        return _b64e(nonce), _b64e(ct)

    def decrypt_secret(self, nonce_b64: str, ciphertext_b64: str, aad: str = "") -> str:
        """Decrypts AES-256-GCM ciphertext."""
        key = self._ensure_vault_key()
        aesgcm = AESGCM(key)
        pt = aesgcm.decrypt(_b64d(nonce_b64), _b64d(ciphertext_b64), aad.encode("utf-8"))
        return pt.decode("utf-8")

    def issue_sovereignty_token(
        self,
        audience: str,
        scope: str,
        claims_digest: str,
        ttl_seconds: int = 300,
    ) -> dict[str, Any]:
        """Signs a short-lived Ed25519 token proving local validation without raw data."""
        assert self._private_key is not None
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=ttl_seconds)
        payload = {
            "iss": self.identity.identity_id,
            "aud": audience,
            "scope": scope,
            "claims_sha256": claims_digest,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": os.urandom(8).hex(),
        }
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = self._private_key.sign(payload_bytes)
        token_string = f"newera1.{_b64e(payload_bytes)}.{_b64e(signature)}"
        return {
            "token": token_string,
            "payload": payload,
            "signature_b64": _b64e(signature),
            "public_key_b64": self.identity.public_key_b64,
            "expires_at": expires.isoformat(),
        }

    def verify_sovereignty_token(self, token_string: str) -> dict[str, Any]:
        """Verifies Ed25519 signature and expiration of a sovereignty token."""
        try:
            prefix, payload_b64, sig_b64 = token_string.split(".")
            if prefix != "newera1":
                return {"valid": False, "reason": "invalid_prefix"}
            payload_bytes = _b64d(payload_b64)
            sig = _b64d(sig_b64)
            pub_raw = _b64d(self.identity.public_key_b64)
            pub = Ed25519PublicKey.from_public_bytes(pub_raw)
            pub.verify(sig, payload_bytes)
            payload = json.loads(payload_bytes.decode("utf-8"))
            now_ts = int(datetime.now(timezone.utc).timestamp())
            if payload.get("exp", 0) < now_ts:
                return {"valid": False, "reason": "expired", "payload": payload}
            return {"valid": True, "payload": payload}
        except Exception as exc:
            return {"valid": False, "reason": str(exc)}
