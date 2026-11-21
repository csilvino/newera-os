"""SemanticFS — Content-addressed object store + FTS5 + Vector index + Semantic Graph."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..models import SemanticObject
from .extractor import build_summary, extract_entities, extract_text_from_bytes
from .vectorizer import cosine_similarity, embed_text, normalize_text, tokenize


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SemanticFS:
    """Folderless semantic file system native to the Newera OS kernel."""

    def __init__(self, db_path: Path, store_dir: Path) -> None:
        self.db_path = db_path
        self.store_dir = store_dir
        self.store_dir.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS semantic_objects (
                    id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    content_text TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    entities_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS semantic_fts USING fts5(
                    obj_id UNINDEXED,
                    title,
                    content_text,
                    entities_text,
                    tags_text
                );
                CREATE TABLE IF NOT EXISTS semantic_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    UNIQUE(source_id, target_id, relation)
                );
                """
            )

    def _write_blob(self, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        blob_path = self.store_dir / digest[:2] / digest
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        if not blob_path.exists():
            blob_path.write_bytes(data)
        return digest

    def read_blob(self, content_hash: str) -> bytes | None:
        blob_path = self.store_dir / content_hash[:2] / content_hash
        if not blob_path.exists():
            return None
        return blob_path.read_bytes()

    def ingest_bytes(
        self,
        data: bytes,
        filename: str,
        mime_type: str = "application/octet-stream",
        title: str | None = None,
        extra_tags: list[str] | None = None,
        extra_people: list[str] | None = None,
        created_at: str | None = None,
    ) -> SemanticObject:
        content_hash = self._write_blob(data)
        text, kind = extract_text_from_bytes(data, filename, mime_type)
        return self._index_object(
            content_hash=content_hash,
            kind=kind,
            title=title or filename,
            content_text=text,
            mime_type=mime_type,
            original_name=filename,
            extra_tags=extra_tags,
            extra_people=extra_people,
            created_at=created_at,
        )

    def ingest_text(
        self,
        title: str,
        content_text: str,
        kind: str = "note",
        extra_tags: list[str] | None = None,
        extra_people: list[str] | None = None,
        created_at: str | None = None,
        related_to: list[str] | None = None,
    ) -> SemanticObject:
        raw = content_text.encode("utf-8")
        content_hash = self._write_blob(raw)
        obj = self._index_object(
            content_hash=content_hash,
            kind=kind,
            title=title,
            content_text=content_text,
            mime_type="text/markdown",
            original_name=f"{title[:40]}.md",
            extra_tags=extra_tags,
            extra_people=extra_people,
            created_at=created_at,
        )
        if related_to:
            for target_id in related_to:
                self.add_relation(obj.id, target_id, "related_to")
        return obj

    def _index_object(
        self,
        content_hash: str,
        kind: str,
        title: str,
        content_text: str,
        mime_type: str,
        original_name: str,
        extra_tags: list[str] | None = None,
        extra_people: list[str] | None = None,
        created_at: str | None = None,
    ) -> SemanticObject:
        obj_id = f"sem_{uuid.uuid4().hex[:10]}"
        ts = created_at or _utc_now()
        entities, tags = extract_entities(title, content_text)
        if extra_tags:
            tags = sorted(set(tags) | {t.lower().strip() for t in extra_tags if t.strip()})
        if extra_people:
            existing_people = set(entities.get("people", []))
            entities["people"] = sorted(existing_people | {p.strip() for p in extra_people if p.strip()})

        summary = build_summary(content_text)
        index_blob = f"{title} {content_text} {' '.join(tags)} {' '.join(entities.get('people', []))}"
        vector = embed_text(index_blob)
        entities_flat = " ".join(v for vals in entities.values() for v in vals)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO semantic_objects
                (id, content_hash, kind, title, summary, content_text, mime_type, original_name,
                 entities_json, tags_json, vector_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    obj_id,
                    content_hash,
                    kind,
                    title,
                    summary,
                    content_text,
                    mime_type,
                    original_name,
                    json.dumps(entities, ensure_ascii=False),
                    json.dumps(tags, ensure_ascii=False),
                    json.dumps(vector),
                    ts,
                    ts,
                ),
            )
            conn.execute(
                "INSERT INTO semantic_fts (obj_id, title, content_text, entities_text, tags_text) VALUES (?, ?, ?, ?, ?)",
                (obj_id, title, content_text, entities_flat, " ".join(tags)),
            )

        # Auto-link with existing objects sharing people or strong semantic similarity
        self._auto_link(obj_id, vector, entities, tags)

        return SemanticObject(
            id=obj_id,
            content_hash=content_hash,
            kind=kind,  # type: ignore[arg-type]
            title=title,
            summary=summary,
            content_text=content_text,
            mime_type=mime_type,
            original_name=original_name,
            entities=entities,
            tags=tags,
            created_at=ts,
            updated_at=ts,
        )

    def _auto_link(
        self,
        new_id: str,
        new_vec: list[float],
        entities: dict[str, list[str]],
        tags: list[str],
    ) -> None:
        new_people = {p.lower() for p in entities.get("people", [])}
        new_tags = set(tags)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, entities_json, tags_json, vector_json FROM semantic_objects WHERE id != ?",
                (new_id,),
            ).fetchall()
        for r in rows:
            other_entities = json.loads(r["entities_json"])
            other_people = {p.lower() for p in other_entities.get("people", [])}
            other_tags = set(json.loads(r["tags_json"]))
            other_vec = json.loads(r["vector_json"])

            if new_people & other_people:
                self.add_relation(new_id, r["id"], "shared_person", weight=0.95)
                continue
            sim = cosine_similarity(new_vec, other_vec)
            if sim >= 0.42:
                self.add_relation(new_id, r["id"], "semantic_match", weight=round(sim, 3))
            elif len(new_tags & other_tags) >= 2:
                self.add_relation(new_id, r["id"], "shared_context", weight=0.65)

    def add_relation(self, source_id: str, target_id: str, relation: str, weight: float = 1.0) -> None:
        if source_id == target_id:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO semantic_relations (source_id, target_id, relation, weight, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source_id, target_id, relation, weight, _utc_now()),
            )

    def get_object(self, obj_id: str) -> SemanticObject | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM semantic_objects WHERE id = ?", (obj_id,)).fetchone()
        return self._row_to_obj(row) if row else None

    def list_objects(self, limit: int = 50) -> list[SemanticObject]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM semantic_objects ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_obj(r) for r in rows]

    def search(self, query: str, limit: int = 10) -> list[SemanticObject]:
        """Hybrid natural language search: Vector similarity + FTS5 + Entities + Relative Time."""
        q_vec = embed_text(query)
        q_norm = normalize_text(query)
        q_tokens = set(tokenize(query))

        # Temporal cues in Portuguese
        now = datetime.now(timezone.utc)
        time_bonus_window: tuple[datetime, datetime] | None = None
        if "semana passada" in q_norm or "ultima semana" in q_norm:
            time_bonus_window = (now - timedelta(days=14), now - timedelta(days=3))
        elif "ontem" in q_norm:
            time_bonus_window = (now - timedelta(days=2), now)
        elif "hoje" in q_norm:
            time_bonus_window = (now - timedelta(hours=24), now)

        # FTS5 candidate boost
        fts_hits: set[str] = set()
        fts_terms = [t for t in q_tokens if len(t) >= 3]
        if fts_terms:
            fts_query = " OR ".join(f"{t}*" for t in fts_terms[:8])
            try:
                with self._connect() as conn:
                    rows = conn.execute(
                        "SELECT obj_id FROM semantic_fts WHERE semantic_fts MATCH ? LIMIT 30",
                        (fts_query,),
                    ).fetchall()
                    fts_hits = {r["obj_id"] for r in rows}
            except sqlite3.OperationalError:
                fts_hits = set()

        with self._connect() as conn:
            all_rows = conn.execute("SELECT * FROM semantic_objects").fetchall()

        scored: list[tuple[float, SemanticObject]] = []
        for r in all_rows:
            vec = json.loads(r["vector_json"])
            sim = max(0.0, cosine_similarity(q_vec, vec))
            score = sim * 0.65

            if r["id"] in fts_hits:
                score += 0.25

            entities = json.loads(r["entities_json"])
            tags = json.loads(r["tags_json"])

            # Entity / person boost (e.g., "João")
            for person in entities.get("people", []):
                p_norm = normalize_text(person)
                if p_norm and any(part in q_norm for part in p_norm.split()):
                    score += 0.35

            # File format / MIME hint (e.g., "PDF")
            if "pdf" in q_norm and (r["mime_type"] == "application/pdf" or r["original_name"].lower().endswith(".pdf")):
                score += 0.20

            # Tag overlap
            for tag in tags:
                if normalize_text(tag) in q_norm:
                    score += 0.12

            # Temporal proximity boost
            if time_bonus_window:
                try:
                    created = datetime.fromisoformat(r["created_at"])
                    if time_bonus_window[0] <= created <= time_bonus_window[1]:
                        score += 0.20
                except ValueError:
                    pass

            if score >= 0.12:
                obj = self._row_to_obj(r)
                obj.score = round(min(score, 1.0), 3)
                scored.append((score, obj))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [obj for _, obj in scored[:limit]]

    def get_graph(self) -> dict[str, Any]:
        """Returns nodes and edges for the interactive Semantic Memory Map."""
        with self._connect() as conn:
            objs = conn.execute(
                "SELECT id, kind, title, summary, entities_json, tags_json, created_at FROM semantic_objects ORDER BY updated_at DESC LIMIT 80"
            ).fetchall()
            rels = conn.execute(
                "SELECT source_id, target_id, relation, weight FROM semantic_relations"
            ).fetchall()

        nodes = []
        entity_nodes: dict[str, dict[str, Any]] = {}
        edges = [
            {
                "source": r["source_id"],
                "target": r["target_id"],
                "relation": r["relation"],
                "weight": r["weight"],
            }
            for r in rels
        ]

        for o in objs:
            entities = json.loads(o["entities_json"])
            tags = json.loads(o["tags_json"])
            nodes.append(
                {
                    "id": o["id"],
                    "label": o["title"],
                    "kind": o["kind"],
                    "summary": o["summary"],
                    "tags": tags,
                    "created_at": o["created_at"],
                }
            )
            for person in entities.get("people", []):
                pid = f"person_{normalize_text(person).replace(' ', '_')}"
                if pid not in entity_nodes:
                    entity_nodes[pid] = {
                        "id": pid,
                        "label": person,
                        "kind": "person",
                        "summary": f"Pessoa conectada no grafo semântico",
                        "tags": ["pessoa"],
                    }
                edges.append(
                    {"source": o["id"], "target": pid, "relation": "mentions_person", "weight": 0.9}
                )

        return {"nodes": nodes + list(entity_nodes.values()), "edges": edges}

    def seed_initial_memories(self) -> int:
        """Populates realistic starter memories only if SemanticFS is empty."""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM semantic_objects").fetchone()[0]
        if count > 0:
            return 0

        last_week = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

        self.ingest_bytes(
            data=(
                "CONTRATO DE PRESTAÇÃO DE SERVIÇOS DE DESIGN E ENGENHARIA\n"
                "Revisado com o João Silva na reunião da semana passada.\n"
                "Valor total acordado: R$ 12.500,00 em duas parcelas.\n"
                "Cláusula 4: Propriedade intelectual aberta sob licença Apache 2.0.\n"
                "Prazo de entrega: 30 dias corridos após assinatura."
            ).encode("utf-8"),
            filename="contrato_servicos_joao.pdf",
            mime_type="application/pdf",
            title="Contrato de Serviços — Revisão com João",
            extra_tags=["contrato", "pdf", "revisao"],
            extra_people=["João"],
            created_at=last_week,
        )
        self.ingest_text(
            title="Notas de Reunião — Arquitetura Newera OS",
            content_text=(
                "Discussão com o João sobre o Open Intent Protocol (OIP).\n"
                "Prioridades: Lentes Cognitivas em 3 camadas, Modo Raio-X (Alt+X) para desenvolvedores "
                "e Guardian Sandbox com tokens Ed25519 sem expor CPF ou dados bancários."
            ),
            kind="note",
            extra_tags=["projeto", "arquitetura", "github"],
            extra_people=["João"],
            created_at=two_days_ago,
        )
        self.ingest_text(
            title="Fatura Estimada — Equipamentos & Nuvem",
            content_text=(
                "Servidor doméstico mini-PC: R$ 1.850,00\n"
                "Domínio e certificados: R$ 120,00\n"
                "Backup criptografado mensal: R$ 85,00"
            ),
            kind="dataset",
            extra_tags=["finanças", "fatura"],
        )
        return 3

    def _row_to_obj(self, row: sqlite3.Row) -> SemanticObject:
        return SemanticObject(
            id=row["id"],
            content_hash=row["content_hash"],
            kind=row["kind"],
            title=row["title"],
            summary=row["summary"],
            content_text=row["content_text"],
            mime_type=row["mime_type"],
            original_name=row["original_name"],
            entities=json.loads(row["entities_json"]),
            tags=json.loads(row["tags_json"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
