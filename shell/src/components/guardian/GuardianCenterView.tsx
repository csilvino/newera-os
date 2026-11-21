import React, { useEffect, useState } from 'react';
import {
  Check,
  Eye,
  KeyRound,
  Lock,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react';
import { api } from '../../services/api';
import type { SystemStatus } from '../../types';

interface Props {
  status: SystemStatus | null;
  onRefreshStatus: () => void;
}

export const GuardianCenterView: React.FC<Props> = ({ status, onRefreshStatus }) => {
  const [vaultItems, setVaultItems] = useState<any[]>([]);
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [tokens, setTokens] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);

  const [vKey, setVKey] = useState('');
  const [vLabel, setVLabel] = useState('');
  const [vValue, setVValue] = useState('');

  const [piiInput, setPiiInput] = useState(
    'Enviar contrato para joao@exemplo.com com CPF 123.456.789-01 e telefone (11) 99876-5432'
  );
  const [piiResult, setPiiResult] = useState<any>(null);

  const loadAll = async () => {
    const [v, t, a] = await Promise.all([api.listVault(), api.listTokens(), api.getAudit()]);
    setVaultItems(v);
    setTokens(t);
    setAudit(a);
    onRefreshStatus();
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleStore = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!vKey.trim() || !vValue.trim()) return;
    await api.storeVault(vKey.trim(), vValue.trim(), 'personal', vLabel.trim() || vKey.trim());
    setVKey('');
    setVLabel('');
    setVValue('');
    await loadAll();
  };

  const handleReveal = async (key: string) => {
    if (revealed[key]) {
      setRevealed((prev) => {
        const copy = { ...prev };
        delete copy[key];
        return copy;
      });
      return;
    }
    const res = await api.revealVault(key);
    setRevealed((prev) => ({ ...prev, [key]: res.value }));
  };

  const handleSimulatePurchaseToken = async () => {
    const keys = vaultItems.slice(0, 1).map((i) => i.key);
    await api.requestToken(
      'checkout.loja-exemplo.com.br',
      'delivery_address_verified',
      keys,
      'Validar entrega sem expor endereço bruto ao site externo'
    );
    await loadAll();
  };

  const handleTestPII = async () => {
    const res = await api.sanitizePII(piiInput);
    setPiiResult(res);
    await loadAll();
  };

  return (
    <div className="max-w-7xl mx-auto px-4 pt-6 pb-16 space-y-6">
      {/* Header */}
      <div className="glass-panel rounded-2xl p-5 flex flex-wrap items-center justify-between gap-4 border-emerald-500/30">
        <div className="flex items-center gap-3">
          <div className="p-3 rounded-xl bg-emerald-500/15 text-emerald-400">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-white">Guardian Sandbox — Soberania &amp; Privacidade</h2>
            <p className="text-xs text-slate-400">
              Identidade: <span className="font-mono text-emerald-300">{status?.guardian.identity.identity_id}</span> ·{' '}
              {status?.guardian.encryption}
            </p>
          </div>
        </div>
        <div className="text-xs font-mono px-3 py-1.5 rounded-xl bg-emerald-950/60 border border-emerald-500/30 text-emerald-300">
          Audit Chain: {status?.guardian.audit_chain_valid ? 'ÍNTEGRA ✓' : 'ALERTA'}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Encrypted Vault */}
        <div className="lg:col-span-6 glass-panel rounded-2xl p-5 space-y-4">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <Lock className="w-4 h-4 text-cyan-400" /> Cofre Pessoal (AES-256-GCM)
          </h3>

          <form onSubmit={handleStore} className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <input
              value={vKey}
              onChange={(e) => setVKey(e.target.value)}
              placeholder="Chave (ex: endereco)"
              className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-cyan-400"
            />
            <input
              value={vValue}
              onChange={(e) => setVValue(e.target.value)}
              placeholder="Valor secreto"
              className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-cyan-400"
            />
            <button
              type="submit"
              className="px-3 py-1.5 rounded-lg bg-cyan-500 text-slate-950 font-semibold text-xs"
            >
              Criptografar no Cofre
            </button>
          </form>

          <div className="space-y-2">
            {vaultItems.length === 0 && (
              <p className="text-xs text-slate-500">
                Cofre vazio. Adicione seu endereço ou dado sensível para testar a tokenização soberana.
              </p>
            )}
            {vaultItems.map((it) => (
              <div
                key={it.key}
                className="rounded-xl bg-slate-900/80 border border-slate-800 p-3 flex items-center justify-between gap-2"
              >
                <div>
                  <div className="text-xs font-semibold text-slate-100">{it.label}</div>
                  <div className="text-[11px] font-mono text-slate-400">
                    {revealed[it.key] ? revealed[it.key] : '•••••••••••••••• (AES-256-GCM)'}
                  </div>
                </div>
                <div className="flex gap-1.5">
                  <button
                    onClick={() => handleReveal(it.key)}
                    className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-cyan-300"
                    title="Revelar localmente"
                  >
                    <Eye className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={async () => {
                      await api.deleteVault(it.key);
                      await loadAll();
                    }}
                    className="p-1.5 rounded-lg bg-slate-800 text-slate-400 hover:text-rose-400"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Sovereignty Tokens */}
        <div className="lg:col-span-6 glass-panel rounded-2xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <KeyRound className="w-4 h-4 text-amber-400" /> Tokens de Soberania (Ed25519)
            </h3>
            <button
              onClick={handleSimulatePurchaseToken}
              className="px-3 py-1.5 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-200 text-xs hover:bg-amber-500/30"
            >
              Simular Pedido Externo
            </button>
          </div>
          <p className="text-xs text-slate-400">
            Quando um site pede seu endereço ou pagamento, o Guardian valida localmente e emite apenas
            um token assinado — nunca seus dados brutos.
          </p>
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {tokens.map((t) => (
              <div key={t.id} className="rounded-xl bg-slate-900/80 border border-slate-800 p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-100">{t.audience}</span>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${
                      t.status === 'approved'
                        ? 'bg-emerald-500/20 text-emerald-300'
                        : t.status === 'denied'
                        ? 'bg-rose-500/20 text-rose-300'
                        : 'bg-amber-500/20 text-amber-300'
                    }`}
                  >
                    {t.status}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400">
                  Escopo: <span className="font-mono text-cyan-300">{t.scope}</span> · {t.reason}
                </div>
                {t.status === 'pending' && (
                  <div className="flex gap-2">
                    <button
                      onClick={async () => {
                        await api.approveToken(t.id);
                        await loadAll();
                      }}
                      className="px-3 py-1 rounded-lg bg-emerald-500 text-slate-950 font-semibold text-xs flex items-center gap-1"
                    >
                      <Check className="w-3.5 h-3.5" /> Aprovar Token Cego
                    </button>
                    <button
                      onClick={async () => {
                        await api.denyToken(t.id);
                        await loadAll();
                      }}
                      className="px-3 py-1 rounded-lg bg-rose-500/20 text-rose-300 text-xs flex items-center gap-1"
                    >
                      <X className="w-3.5 h-3.5" /> Recusar
                    </button>
                  </div>
                )}
                {t.token && (
                  <div className="text-[10px] font-mono bg-slate-950 p-2 rounded-lg text-emerald-300 break-all">
                    {t.token}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Live PII Proxy */}
        <div className="lg:col-span-6 glass-panel rounded-2xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-cyan-400" /> Proxy Local de Proteção de PII
          </h3>
          <textarea
            value={piiInput}
            onChange={(e) => setPiiInput(e.target.value)}
            rows={3}
            className="w-full bg-slate-900 border border-slate-700 rounded-xl p-3 text-xs text-slate-100 outline-none focus:border-cyan-400"
          />
          <button
            onClick={handleTestPII}
            className="px-4 py-1.5 rounded-lg bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 text-xs font-medium"
          >
            Inspecionar e Mascarar Saída
          </button>
          {piiResult && (
            <div className="rounded-xl bg-slate-950 border border-emerald-500/30 p-3 space-y-1">
              <div className="text-[11px] text-emerald-400 font-semibold">
                {piiResult.redacted_count} dado(s) pessoal(is) bloqueado(s) antes de sair do dispositivo:
              </div>
              <div className="text-xs font-mono text-slate-200">{piiResult.sanitized_text}</div>
            </div>
          )}
        </div>

        {/* Chained Audit Log */}
        <div className="lg:col-span-6 glass-panel rounded-2xl p-5 space-y-3">
          <h3 className="text-sm font-semibold text-white">Log de Auditoria Encadeado (SHA-256)</h3>
          <div className="space-y-1.5 max-h-56 overflow-y-auto">
            {audit.map((ev) => (
              <div
                key={ev.event_id}
                className="rounded-lg bg-slate-900/70 border border-slate-800 px-3 py-2 text-[11px] flex items-center justify-between gap-2"
              >
                <div>
                  <span className="font-mono text-cyan-300">{ev.action}</span>{' '}
                  <span className="text-slate-400">por {ev.actor}</span>
                </div>
                <span className="font-mono text-slate-500">#{ev.entry_hash}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
