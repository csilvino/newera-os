# Segurança e Privacidade — Newera OS

A segurança do **Newera OS** é garantida pelo subsistema **Guardian Sandbox** (`kernel/guardian/`):

1. **Identidade Criptográfica Local:** Cada instalação gera localmente um par de chaves **Ed25519** em `data/guardian/` (nunca versionado no Git).
2. **Cofre em Repouso:** Segredos armazenados no cofre são cifrados com **AES-256-GCM** com nonce aleatório de 96 bits e dados autenticados (AAD). A listagem de itens nunca retorna o texto plano.
3. **Proxy de PII:** Qualquer texto destinado a um serviço externo ou LLM opcional passa obrigatoriamente por `guardian.sanitize_outbound(...)`, que detecta e substitui CPF, CNPJ, cartões (validados por Luhn), e-mails, telefones, CEPs e chaves de API por pseudônimos locais.
4. **Tokens de Soberania:** Serviços externos recebem apenas tokens `newera1.<payload>.<signature>` assinados com Ed25519 contendo o hash cego das claims e prazo curto de expiração — nunca os dados brutos.
5. **Auditoria Encadeada:** Todas as ações críticas são gravadas em `audit_log` com encadeamento SHA-256 verificável (`verify_audit_chain`).

Para reportar vulnerabilidades, abra um aviso de segurança privado no repositório GitHub.
