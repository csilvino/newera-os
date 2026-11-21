# Open Intent Protocol (OIP) — Especificação v0.1

O **Open Intent Protocol (OIP)** define os contratos abertos que conectam intenções humanas, motores de capacidade, memória semântica e soberania de privacidade no **Newera OS**.

---

## 1. Objeto de Intenção (`IntentRequest`)
Representa o que o humano quer realizar, em linguagem natural (texto ou voz), independente de qual software tradicional seria usado.

```json
{
  "query": "planejar uma viagem de 5 dias para Florianópolis com orçamento de R$ 4.000",
  "locale": "pt-BR",
  "device_type": "desktop",
  "workspace_id": null,
  "context_refs": []
}
```

---

## 2. Grafo de Workspace Efêmero (`WorkspaceGraph`)
É a saída do `Intent Engine`. O Shell Generativo renderiza este grafo em 3 **Lentes Cognitivas** (`essence`, `work`, `xray`).

```json
{
  "id": "ws_abc123",
  "title": "Viagem — Florianópolis (5 dias)",
  "intent_type": "travel_planning",
  "status": "active",
  "essence": {
    "headline": "Roteiro de 5 dias pronto dentro de R$ 4.000",
    "metrics": [
      { "label": "Orçamento", "value": "R$ 4.000", "status": "ok" }
    ]
  },
  "blocks": [
    {
      "id": "blk_budget",
      "type": "budget_sheet",
      "title": "Planilha Dinâmica de Custos",
      "capability": "calc_engine",
      "col_span": 7,
      "data": {}
    }
  ],
  "wires": [
    {
      "from_block": "blk_budget",
      "from_field": "total",
      "to_block": "blk_summary",
      "to_field": "spent",
      "label": "Atualiza saldo em tempo real"
    }
  ],
  "trace": [],
  "version": 1
}
```

---

## 3. Manifesto de Capacidade (`capability.yaml`)
Permite que qualquer desenvolvedor adicione uma nova capacidade ao Newera OS em uma pasta autocontida sob `kernel/capabilities/contrib/<id>/`.

```yaml
id: my_capability
name: Minha Capacidade
version: "0.1.0"
description: Descrição objetiva do que esta capacidade resolve
intents:
  - my_intent
keywords:
  - palavra_chave
permissions:
  network: false
  vault: none          # none | token_only
  semantic_fs: read    # none | read | read_write
```

---

## 4. Objeto Semântico (`SemanticObject`)
Unidade fundamental do `SemanticFS` — substitui o conceito de "arquivo dentro de pasta".

- `id`: identificador único do nó
- `content_hash`: SHA-256 do conteúdo bruto (content-addressed)
- `kind`: `document | note | workspace_archive | dataset | media`
- `title`, `summary`, `content_text`
- `entities`: pessoas, locais, datas, valores monetários, tags
- `relations`: arestas tipadas (`mentions`, `created_in`, `related_to`, `derived_from`)

---

## 5. Token de Soberania (`SovereigntyToken`)
Emitido pelo `Guardian Sandbox` quando um serviço externo solicita validação sem expor dados brutos do usuário.

- Assinado criptograficamente com a chave privada **Ed25519** da identidade local.
- Possui `scope` mínimo, `audience`, `expires_at` curto e `payload_hash` (nunca o dado bruto).
- Toda emissão é gravada no **Audit Log com hash encadeado**.
