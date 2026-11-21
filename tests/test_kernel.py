"""End-to-end automated tests for all 4 pillars of Newera OS Kernel."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from kernel.app import create_app


def _make_client(tmp_path: Path) -> TestClient:
    app = create_app(data_dir=tmp_path / "newera_data")
    return TestClient(app)


def test_pillar1_generative_travel_workspace_and_refinement(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.post(
        "/api/intent",
        json={"query": "planejar uma viagem de 5 dias para Florianópolis com orçamento de R$ 4.000"},
    )
    assert resp.status_code == 200
    ws = resp.json()
    assert ws["intent_type"] == "travel_planning"
    block_types = {b["type"] for b in ws["blocks"]}
    assert {"budget_sheet", "map_weather", "checklist_timeline"}.issubset(block_types)
    assert len(ws["wires"]) >= 2
    assert len(ws["trace"]) >= 4
    assert ws["version"] == 1

    # Refine budget via natural language
    r2 = client.post(
        f"/api/workspaces/{ws['id']}/refine",
        json={"command": "reduza o orçamento para R$ 3.200"},
    )
    assert r2.status_code == 200
    ws2 = r2.json()
    assert ws2["version"] == 2
    assert len(ws2["history"]) == 2

    # Time-Travel restore to version 1
    r3 = client.post(f"/api/workspaces/{ws['id']}/restore/1")
    assert r3.status_code == 200
    ws_restored = r3.json()
    budget_blk = next(b for b in ws_restored["blocks"] if b["type"] == "budget_sheet")
    assert budget_blk["data"]["budget_limit"] == 4000.0


def test_pillar1_contrib_sdk_auto_discovery(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    status = client.get("/api/system/status").json()
    cap_ids = {c["id"] for c in status["capabilities"]}
    assert "focus_pomodoro" in cap_ids

    resp = client.post("/api/intent", json={"query": "quero entrar em modo foco pomodoro 30 minutos"})
    assert resp.status_code == 200
    ws = resp.json()
    assert ws["intent_type"] == "focus_session"
    assert any(b["type"] == "focus_timer" for b in ws["blocks"])


def test_pillar2_semantic_fs_folderless_search_and_intent_physics(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    # Seeded memory test: "contrato em PDF que revisei semana passada com o João"
    search = client.get("/api/semantic/search", params={"q": "contrato em PDF que revisei semana passada com o João"})
    assert search.status_code == 200
    hits = search.json()
    assert len(hits) >= 1
    assert "João" in hits[0]["title"] or "contrato" in hits[0]["title"].lower()

    # Upload a new text/invoice file without any folder
    upload = client.post(
        "/api/semantic/upload",
        files={"file": ("fatura_hotel.txt", b"Diaria extra resort: R$ 450,00\nTranslado aeroporto: R$ 120,00", "text/plain")},
        data={"tags": "viagem,fatura", "people": "Maria"},
    )
    assert upload.status_code == 200
    uploaded_id = upload.json()["id"]

    # Intent Physics: merge uploaded invoice into active budget sheet
    ws = client.post("/api/intent", json={"query": "orçamento de R$ 2.000"}).json()
    merge = client.post(
        f"/api/workspaces/{ws['id']}/merge",
        json={"block_id": "blk_budget", "semantic_object_id": uploaded_id},
    )
    assert merge.status_code == 200
    merged_ws = merge.json()["workspace"]
    budget_blk = next(b for b in merged_ws["blocks"] if b["id"] == "blk_budget")
    assert any("Diaria extra resort" in r["item"] for r in budget_blk["data"]["rows"])

    # Graph endpoint returns nodes and edges
    graph = client.get("/api/semantic/graph").json()
    assert len(graph["nodes"]) >= 4
    assert len(graph["edges"]) >= 2


def test_pillar3_continuum_handoff_and_dissolve(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    ws = client.post("/api/intent", json={"query": "planejar projeto open source"}).json()
    handoff = client.get("/api/continuum/handoff", params={"workspace_id": ws["id"]}).json()
    assert "<svg" in handoff["qr_svg"]
    assert ws["id"] in handoff["url"]

    dissolved = client.post(f"/api/workspaces/{ws['id']}/dissolve").json()
    assert dissolved["status"] == "dissolved"
    assert dissolved["archived_semantic_id"].startswith("sem_")


def test_pillar4_guardian_vault_pii_and_sovereignty_tokens(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    # Store encrypted secret
    store = client.post(
        "/api/guardian/vault",
        json={"key": "endereco_casa", "value": "Av. Paulista, 1000 - São Paulo", "category": "address", "label": "Endereço Residencial"},
    )
    assert store.status_code == 200

    # List never returns raw secret value
    items = client.get("/api/guardian/vault").json()
    assert len(items) == 1
    assert "value" not in items[0]

    # Local reveal works
    revealed = client.get("/api/guardian/vault/endereco_casa/reveal").json()
    assert revealed["value"] == "Av. Paulista, 1000 - São Paulo"

    # PII outbound proxy redacts CPF and email
    pii = client.post(
        "/api/guardian/proxy/sanitize",
        json={"text": "Meu CPF é 123.456.789-01 e meu email é joao@exemplo.com"},
    ).json()
    assert pii["redacted_count"] == 2
    assert "123.456.789-01" not in pii["sanitized_text"]
    assert "joao@exemplo.com" not in pii["sanitized_text"]

    # Sovereignty Token request -> approve -> cryptographic Ed25519 verify
    req = client.post(
        "/api/guardian/tokens/request",
        json={
            "audience": "loja-exemplo.com.br",
            "scope": "delivery_address_verified",
            "vault_keys": ["endereco_casa"],
            "reason": "Confirmar entrega sem expor endereço bruto",
        },
    ).json()
    assert req["status"] == "pending"

    approved = client.post(f"/api/guardian/tokens/{req['id']}/approve").json()
    assert approved["status"] == "approved"
    assert approved["raw_data_exposed"] is False
    assert approved["token"].startswith("newera1.")

    verified = client.post("/api/guardian/tokens/verify", json={"token": approved["token"]}).json()
    assert verified["valid"] is True
    assert verified["payload"]["aud"] == "loja-exemplo.com.br"

    # Audit log hash chain integrity
    status = client.get("/api/guardian/status").json()
    assert status["audit_chain_valid"] is True
    assert status["audit_events_count"] >= 4
