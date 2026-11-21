"""Guardian Sandbox Service — Vault, Sovereignty Tokens, PII Proxy, Chained Audit Log."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .crypto import CryptoEngine
from .pii import inspect_and_redact


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GuardianService:
    """Personal privacy guardian sitting between the user and any external service."""

    def __init__(self, guardian_dir: Path, db_path: Path) -> None:
        self.crypto = CryptoEngine(guardian_dir)
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS vault_items (
                    key TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    label TEXT NOT NULL,
                    nonce_b64 TEXT NOT NULL,
                    ciphertext_b64 TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS token_approvals (
                    id TEXT PRIMARY KEY,
                    audience TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    vault_keys TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    ttl_seconds INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    token TEXT,
                    expires_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL
                );
                """
            )

    def _append_audit(self, action: str, actor: str, detail: dict[str, Any]) -> dict[str, Any]:
        ts = _utc_now()
        event_id = f"aud_{uuid.uuid4().hex[:10]}"
        detail_json = json.dumps(detail, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prev_hash = row["entry_hash"] if row else "0" * 64
            payload = f"{prev_hash}|{event_id}|{ts}|{action}|{actor}|{detail_json}"
            entry_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            conn.execute(
                """
                INSERT INTO audit_log (event_id, timestamp, action, actor, detail, prev_hash, entry_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, ts, action, actor, detail_json, prev_hash, entry_hash),
            )
        return {
            "event_id": event_id,
            "timestamp": ts,
            "action": action,
            "actor": actor,
            "detail": detail,
            "entry_hash": entry_hash[:16],
        }

    def get_status(self) -> dict[str, Any]:
        with self._connect() as conn:
            vault_count = conn.execute("SELECT COUNT(*) FROM vault_items").fetchone()[0]
            pending_count = conn.execute(
                "SELECT COUNT(*) FROM token_approvals WHERE status = 'pending'"
            ).fetchone()[0]
            audit_count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        return {
            "identity": {
                "identity_id": self.crypto.identity.identity_id,
                "fingerprint": self.crypto.identity.fingerprint,
                "public_key_b64": self.crypto.identity.public_key_b64,
                "created_at": self.crypto.identity.created_at,
            },
            "encryption": "AES-256-GCM + Ed25519",
            "vault_items_count": vault_count,
            "pending_approvals": pending_count,
            "audit_events_count": audit_count,
            "audit_chain_valid": self.verify_audit_chain(),
        }

    # --- Encrypted Vault ---
    def store_vault_item(self, key: str, value: str, category: str = "personal", label: str = "") -> dict[str, Any]:
        clean_key = key.strip().lower().replace(" ", "_")
        nonce_b64, ct_b64 = self.crypto.encrypt_secret(value, aad=clean_key)
        ts = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO vault_items (key, category, label, nonce_b64, ciphertext_b64, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    category=excluded.category,
                    label=excluded.label,
                    nonce_b64=excluded.nonce_b64,
                    ciphertext_b64=excluded.ciphertext_b64,
                    updated_at=excluded.updated_at
                """,
                (clean_key, category, label or clean_key, nonce_b64, ct_b64, ts),
            )
        self._append_audit("vault.store", "user", {"key": clean_key, "category": category})
        return {"key": clean_key, "category": category, "label": label or clean_key, "updated_at": ts}

    def list_vault_items(self) -> list[dict[str, Any]]:
        """Lists vault metadata ONLY — never exposes raw plaintext by default."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT key, category, label, updated_at FROM vault_items ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def reveal_vault_item(self, key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT key, category, label, nonce_b64, ciphertext_b64, updated_at FROM vault_items WHERE key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        value = self.crypto.decrypt_secret(row["nonce_b64"], row["ciphertext_b64"], aad=row["key"])
        self._append_audit("vault.reveal_local", "user", {"key": key})
        return {
            "key": row["key"],
            "category": row["category"],
            "label": row["label"],
            "value": value,
            "updated_at": row["updated_at"],
        }

    def delete_vault_item(self, key: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM vault_items WHERE key = ?", (key,))
        if cur.rowcount > 0:
            self._append_audit("vault.delete", "user", {"key": key})
            return True
        return False

    # --- PII Outbound Proxy ---
    def sanitize_outbound(self, text: str, target: str = "external_service") -> dict[str, Any]:
        redacted, matches = inspect_and_redact(text)
        summary = [{"kind": m.kind, "replacement": m.replacement} for m in matches]
        if matches:
            self._append_audit(
                "proxy.pii_redacted",
                "guardian",
                {"target": target, "redacted_count": len(matches), "kinds": sorted({m.kind for m in matches})},
            )
        return {
            "sanitized_text": redacted,
            "redacted_count": len(matches),
            "findings": summary,
            "safe_to_send": True,
        }

    # --- Sovereignty Tokens (Zero Raw Data Exposure) ---
    def request_sovereignty_token(
        self,
        audience: str,
        scope: str,
        vault_keys: list[str],
        ttl_seconds: int = 300,
        reason: str = "",
        auto_approve: bool = False,
    ) -> dict[str, Any]:
        req_id = f"req_{uuid.uuid4().hex[:10]}"
        ts = _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO token_approvals
                (id, audience, scope, vault_keys, reason, ttl_seconds, status, token, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, ?)
                """,
                (req_id, audience, scope, json.dumps(vault_keys), reason, ttl_seconds, ts),
            )
        self._append_audit(
            "token.requested",
            audience,
            {"request_id": req_id, "scope": scope, "vault_keys": vault_keys},
        )
        if auto_approve:
            return self.approve_token_request(req_id)
        return {
            "id": req_id,
            "audience": audience,
            "scope": scope,
            "vault_keys": vault_keys,
            "reason": reason,
            "status": "pending",
            "created_at": ts,
        }

    def approve_token_request(self, request_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM token_approvals WHERE id = ?", (request_id,)
            ).fetchone()
        if not row:
            raise ValueError(f"Token request not found: {request_id}")

        vault_keys: list[str] = json.loads(row["vault_keys"])
        # Validate referenced vault items locally and compute a blinded digest (never sending raw data)
        claims_material: dict[str, str] = {}
        for k in vault_keys:
            item = self.reveal_vault_item(k)
            if item:
                claims_material[k] = hashlib.sha256(item["value"].encode("utf-8")).hexdigest()
        claims_digest = hashlib.sha256(
            json.dumps(claims_material, sort_keys=True).encode("utf-8")
        ).hexdigest()

        issued = self.crypto.issue_sovereignty_token(
            audience=row["audience"],
            scope=row["scope"],
            claims_digest=claims_digest,
            ttl_seconds=row["ttl_seconds"],
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE token_approvals
                SET status = 'approved', token = ?, expires_at = ?
                WHERE id = ?
                """,
                (issued["token"], issued["expires_at"], request_id),
            )
        self._append_audit(
            "token.approved",
            "user",
            {"request_id": request_id, "audience": row["audience"], "scope": row["scope"]},
        )
        return {
            "id": request_id,
            "audience": row["audience"],
            "scope": row["scope"],
            "status": "approved",
            "token": issued["token"],
            "expires_at": issued["expires_at"],
            "raw_data_exposed": False,
        }

    def deny_token_request(self, request_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                "UPDATE token_approvals SET status = 'denied' WHERE id = ?",
                (request_id,),
            )
        self._append_audit("token.denied", "user", {"request_id": request_id})
        return {"id": request_id, "status": "denied"}

    def list_token_requests(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM token_approvals ORDER BY created_at DESC LIMIT 30"
            ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["vault_keys"] = json.loads(item["vault_keys"])
            result.append(item)
        return result

    def verify_token(self, token: str) -> dict[str, Any]:
        return self.crypto.verify_sovereignty_token(token)

    # --- Chained Audit Log ---
    def get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_id, timestamp, action, actor, detail, prev_hash, entry_hash FROM audit_log ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
        items = []
        for r in rows:
            items.append(
                {
                    "event_id": r["event_id"],
                    "timestamp": r["timestamp"],
                    "action": r["action"],
                    "actor": r["actor"],
                    "detail": json.loads(r["detail"]),
                    "entry_hash": r["entry_hash"][:16],
                }
            )
        return items

    def verify_audit_chain(self) -> bool:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT event_id, timestamp, action, actor, detail, prev_hash, entry_hash FROM audit_log ORDER BY seq ASC"
            ).fetchall()
        expected_prev = "0" * 64
        for r in rows:
            if r["prev_hash"] != expected_prev:
                return False
            payload = f"{r['prev_hash']}|{r['event_id']}|{r['timestamp']}|{r['action']}|{r['actor']}|{r['detail']}"
            calc = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if calc != r["entry_hash"]:
                return False
            expected_prev = calc
        return True
