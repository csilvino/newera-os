import React, { useState } from 'react';
import { Code2, Cpu, ShieldCheck, X } from 'lucide-react';
import type { SystemStatus, WorkspaceGraph } from '../../types';

interface Props {
  open: boolean;
  onClose: () => void;
  status: SystemStatus | null;
  workspace: WorkspaceGraph | null;
}

export const DevXRayOverlay: React.FC<Props> = ({ open, onClose, status, workspace }) => {
  const [tab, setTab] = useState<'trace' | 'capabilities' | 'schema'>('trace');

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4">
      <div className="glass-panel rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col border-cyan-500/40 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Code2 className="w-5 h-5 text-cyan-400" />
            <div>
              <h3 className="text-sm font-semibold text-white">
                Modo Desenvolvedor Raio-X (Alt+X) — Inspetor Vivo do Kernel
              </h3>
              <p className="text-[11px] text-slate-400">
                Open Intent Protocol (OIP v0.1) · Provedor de IA: {status?.llm_provider || 'local'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 px-5 pt-3 border-b border-slate-800">
          {([
            { id: 'trace', label: 'Trace de Execução' },
            { id: 'capabilities', label: `SDK Capacidades (${status?.capabilities.length || 0})` },
            { id: 'schema', label: 'Workspace JSON (OIP)' },
          ] as const).map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
                tab === t.id
                  ? 'border-cyan-400 text-cyan-300'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto flex-1 space-y-3">
          {tab === 'trace' && (
            <>
              {!workspace ? (
                <p className="text-xs text-slate-400">
                  Gere um workspace no Horizonte para inspecionar o pipeline de execução em milissegundos.
                </p>
              ) : (
                <div className="space-y-2">
                  {workspace.trace.map((step, i) => (
                    <div
                      key={i}
                      className="rounded-xl bg-slate-900/90 border border-slate-800 p-3 flex items-start justify-between gap-3"
                    >
                      <div>
                        <div className="text-xs font-semibold text-cyan-300">{step.step}</div>
                        <div className="text-[11px] font-mono text-slate-500">{step.component}</div>
                        <div className="text-xs text-slate-300 mt-1">{step.detail}</div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-xs font-mono text-emerald-400">{step.duration_ms} ms</div>
                        {step.privacy_checked && (
                          <div className="inline-flex items-center gap-1 text-[10px] text-emerald-300 mt-1">
                            <ShieldCheck className="w-3 h-3" /> Guardian OK
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {tab === 'capabilities' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {(status?.capabilities || []).map((cap) => (
                <div key={cap.id} className="rounded-xl bg-slate-900/90 border border-slate-800 p-3.5">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-white flex items-center gap-1.5">
                      <Cpu className="w-3.5 h-3.5 text-cyan-400" /> {cap.name}
                    </span>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${
                        cap.source === 'contrib'
                          ? 'bg-indigo-500/20 text-indigo-300'
                          : 'bg-slate-800 text-slate-300'
                      }`}
                    >
                      {cap.source}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mb-2">{cap.description}</p>
                  <div className="text-[10px] font-mono text-slate-400 space-y-0.5">
                    <div>id: {cap.id} · v{cap.version}</div>
                    <div>
                      perms: net={String(cap.permissions.network)} · vault={cap.permissions.vault} · fs={cap.permissions.semantic_fs}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {tab === 'schema' && (
            <pre className="rounded-xl bg-slate-950 border border-slate-800 p-4 text-[11px] font-mono text-cyan-200 overflow-x-auto">
              {workspace
                ? JSON.stringify(workspace, null, 2)
                : '// Nenhum workspace ativo no momento'}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
};
