import React, { useEffect, useState } from 'react';
import {
  Code2,
  Compass,
  Network,
  ShieldCheck,
  Smartphone,
  Sparkles,
} from 'lucide-react';
import { GenerativeCanvas } from './components/canvas/GenerativeCanvas';
import { ContinuumModal } from './components/continuum/ContinuumModal';
import { GuardianCenterView } from './components/guardian/GuardianCenterView';
import { HorizonView } from './components/horizon/HorizonView';
import { SemanticMemoryView } from './components/semantic/SemanticMemoryView';
import { DevXRayOverlay } from './components/xray/DevXRayOverlay';
import { api } from './services/api';
import type {
  CognitiveLens,
  SemanticObject,
  ShellView,
  SystemStatus,
  WorkspaceGraph,
} from './types';

export default function App() {
  const [view, setView] = useState<ShellView>('horizon');
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceGraph | null>(null);
  const [memories, setMemories] = useState<SemanticObject[]>([]);
  const [lens, setLens] = useState<CognitiveLens>('work');
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [xrayOpen, setXrayOpen] = useState(false);
  const [continuumOpen, setContinuumOpen] = useState(false);

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 4000);
  };

  const refreshStatus = async () => {
    try {
      const [s, mems] = await Promise.all([api.getStatus(), api.listSemantic()]);
      setStatus(s);
      setMemories(mems);
    } catch {
      // Kernel still starting
    }
  };

  // Boot + Deep Link for Continuum Mobile Handoff (?ws=...)
  useEffect(() => {
    refreshStatus();
    const params = new URLSearchParams(window.location.search);
    const wsId = params.get('ws');
    if (wsId) {
      api.getWorkspace(wsId).then((ws) => {
        setWorkspace(ws);
        setView('canvas');
      }).catch(() => {});
    }
  }, []);

  // Global Alt+X shortcut for Developer X-Ray Inspector
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && e.key.toLowerCase() === 'x') {
        e.preventDefault();
        setXrayOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Live WebSocket sync for Continuum multi-device continuity
  useEffect(() => {
    const isMobile = window.innerWidth < 768 || new URLSearchParams(window.location.search).get('device') === 'mobile';
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = `${proto}://${window.location.host}/ws/continuum?device_type=${isMobile ? 'mobile' : 'desktop'}&device_name=${encodeURIComponent(isMobile ? 'Terminal Mobile' : 'Terminal Desktop')}`;
    const socket = new WebSocket(wsUrl);

    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'workspace_sync' && msg.workspace) {
          setWorkspace((curr) => (curr && curr.id === msg.workspace.id ? msg.workspace : curr));
          refreshStatus();
        } else if (msg.type === 'presence_update') {
          setStatus((curr) => (curr ? { ...curr, connected_devices: msg.devices } : curr));
        }
      } catch {
        // ignore malformed frames
      }
    };

    return () => socket.close();
  }, []);

  const handleIntent = async (query: string) => {
    setLoading(true);
    try {
      const ws = await api.runIntent(query, window.innerWidth < 768 ? 'mobile' : 'desktop');
      setWorkspace(ws);
      setLens('work');
      setView('canvas');
      await refreshStatus();
    } catch (err: any) {
      showToast(`Erro ao compor intenção: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenWorkspace = async (id: string) => {
    const ws = await api.getWorkspace(id);
    setWorkspace(ws);
    setView('canvas');
  };

  const handleRefine = async (command: string) => {
    if (!workspace) return;
    const updated = await api.refineWorkspace(workspace.id, command);
    setWorkspace(updated);
    showToast('Interface atualizada a partir da sua intenção.');
  };

  const handleUpdateBlock = async (blockId: string, data: Record<string, any>, summary: string) => {
    if (!workspace) return;
    const updated = await api.updateBlock(workspace.id, blockId, data, summary);
    setWorkspace(updated);
  };

  const handlePhysicsMerge = async (blockId: string, semanticId: string) => {
    if (!workspace) return;
    const res = await api.mergeSemanticIntoBlock(workspace.id, blockId, semanticId);
    setWorkspace(res.workspace);
    showToast(res.message);
  };

  const handleRestoreVersion = async (version: number) => {
    if (!workspace) return;
    const restored = await api.restoreSnapshot(workspace.id, version);
    setWorkspace(restored);
    showToast(`Time-Travel: restaurado para versão v${version}`);
  };

  const handleDissolve = async () => {
    if (!workspace) return;
    await api.dissolveWorkspace(workspace.id);
    setWorkspace(null);
    setView('horizon');
    await refreshStatus();
    showToast('Interface dissolvida e arquivada automaticamente no SemanticFS.');
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Minimal OS Top Bar (zero clutter, zero start menu) */}
      <header className="sticky top-0 z-40 glass-panel border-t-0 border-x-0 px-4 py-2.5">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-2">
          <button
            onClick={() => setView('horizon')}
            className="flex items-center gap-2 text-left group"
          >
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-cyan-400 to-indigo-500 flex items-center justify-center text-slate-950 font-bold text-xs">
              N
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight text-white leading-none">
                Newera <span className="text-cyan-400">OS</span>
              </div>
              <div className="text-[10px] text-slate-400">Intent-Based Runtime</div>
            </div>
          </button>

          {/* Core Navigation Pills */}
          <nav className="flex items-center gap-1">
            {([
              { id: 'horizon' as ShellView, label: 'Horizonte', icon: Compass },
              ...(workspace ? [{ id: 'canvas' as ShellView, label: 'Canvas Vivo', icon: Sparkles }] : []),
              { id: 'semantic' as ShellView, label: 'SemanticFS', icon: Network },
              { id: 'guardian' as ShellView, label: 'Guardian', icon: ShieldCheck },
            ]).map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setView(id)}
                className={`px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 transition-all ${
                  view === id
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">{label}</span>
              </button>
            ))}
          </nav>

          {/* Continuum & Dev X-Ray Quick Triggers */}
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setContinuumOpen(true)}
              className="px-2.5 py-1.5 rounded-xl bg-slate-900/80 border border-slate-700 hover:border-cyan-400/50 text-xs text-slate-200 flex items-center gap-1.5"
              title="Continuar no celular via QR Code"
            >
              <Smartphone className="w-3.5 h-3.5 text-cyan-400" />
              <span className="hidden md:inline font-mono text-[11px]">
                {status?.connected_devices.length || 1} term.
              </span>
            </button>

            <button
              onClick={() => setXrayOpen(true)}
              className="px-2.5 py-1.5 rounded-xl bg-slate-900/80 border border-slate-700 hover:border-indigo-400/60 text-xs text-indigo-300 flex items-center gap-1.5"
              title="Inspetor Vivo do Kernel (Alt+X)"
            >
              <Code2 className="w-3.5 h-3.5" />
              <span className="hidden md:inline font-mono text-[11px]">Alt+X</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1">
        {view === 'horizon' && (
          <HorizonView
            status={status}
            loading={loading}
            onSubmitIntent={handleIntent}
            onOpenWorkspace={handleOpenWorkspace}
          />
        )}
        {view === 'canvas' && workspace && (
          <GenerativeCanvas
            workspace={workspace}
            memories={memories}
            lens={lens}
            onLensChange={setLens}
            onRefine={handleRefine}
            onUpdateBlock={handleUpdateBlock}
            onPhysicsMerge={handlePhysicsMerge}
            onRestoreVersion={handleRestoreVersion}
            onDissolve={handleDissolve}
            onBackHome={() => setView('horizon')}
          />
        )}
        {view === 'semantic' && <SemanticMemoryView onOpenInWorkspace={handleIntent} />}
        {view === 'guardian' && (
          <GuardianCenterView status={status} onRefreshStatus={refreshStatus} />
        )}
      </main>

      {/* Toast feedback */}
      {toast && (
        <div className="fixed top-16 right-4 z-50 glass-panel border-cyan-400/50 text-cyan-100 text-xs px-4 py-2.5 rounded-xl shadow-xl">
          {toast}
        </div>
      )}

      {/* Overlays */}
      <DevXRayOverlay
        open={xrayOpen}
        onClose={() => setXrayOpen(false)}
        status={status}
        workspace={workspace}
      />
      <ContinuumModal
        open={continuumOpen}
        onClose={() => setContinuumOpen(false)}
        workspaceId={workspace?.id}
      />
    </div>
  );
}
