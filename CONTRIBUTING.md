# Contribuindo para o Newera OS

Bem-vindo! O **Newera OS** foi projetado para que qualquer pessoa possa adicionar uma **nova capacidade** ao sistema operacional sem precisar construir um aplicativo inteiro.

## Crie sua primeira Capacidade em 15 minutos

1. Crie uma pasta em `kernel/capabilities/contrib/<id_da_capacidade>/`.
2. Adicione um manifesto `capability.yaml` declarando intenções, palavras-chave e permissões mínimas:

```yaml
id: minha_capacidade
name: "Minha Capacidade"
version: "0.1.0"
description: "O que esta capacidade resolve para o usuário."
intents:
  - minha_intencao
keywords:
  - palavra_gatilho
permissions:
  network: false
  vault: none
  semantic_fs: read
```

3. Crie `engine.py` implementando `CapabilityEngine` e expondo `create_capability(manifest)` (veja o exemplo pronto em `kernel/capabilities/contrib/focus_pomodoro/`).
4. Reinicie o núcleo — o `CapabilityRegistry` descobrirá sua capacidade automaticamente e ela aparecerá no **Inspetor Raio-X (`Alt+X`)**!

## Rodando os Testes Antes de Abrir um Pull Request

```bash
pytest -v
cd shell && npm run build
```

## Ideias de Good First Issues
- Novos extratores para o `SemanticFS` (DOCX, áudio/transcrição, OCR local).
- Novas capacidades `contrib` (estúdio de música, saúde/exames, automação residencial).
- Novos widgets visuais para o `GenerativeCanvas`.
- Reescrita de módulos críticos (vetorização/criptografia) em Rust via PyO3.
