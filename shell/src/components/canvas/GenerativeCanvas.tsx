import React, { useState } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  Cpu,
  Eye,
  GitBranch,
  History,
  Layers,
  Magnet,
  Send,
  Sparkles,
  Trash2,
} from 'lucide-react';
import type { CognitiveLens, SemanticObject, WorkspaceBlock, WorkspaceGraph } from '../../types';
import { BudgetBlock } from './BudgetBlock';
import { ChecklistBlock } from './ChecklistBlock';
import { DocEditorBlock } from './DocEditorBlock';
import { FocusTimerBlock } from './FocusTimerBlock';
import { MapWeatherBlock } from './MapWeatherBlock';
import { SemanticViewerBlock } from './SemanticViewerBlock';

interface Props {
  workspace: WorkspaceGraph;
  memories: SemanticObject[];
  lens: CognitiveLens;
  onLensChange: (lens: CognitiveLens) => void;
  onRefine: (command: string) => Promise<void>;
  onUpdateBlock: (blockId: string, data: Record<string, any>, summary: string) => Promise<void>;
  onPhysicsMerge: (blockId: string, semanticId: string) => Promise<void>;
  onRestoreVersion: (version: number) => Promise<void>;
  onDissolve: () => Promise<void>;
  onBackHome: () => void;
}

export const GenerativeCanvas: React.FC<Props> = ({
  workspace,
  memories,
  lens,
  onLensChange,
  onRefine,
  onUpdateBlock,
  onPhysicsMerge,
  onRestoreVersion,
  onDissolve,
  onBackHome,
}) => {
  const [refineCmd, setRefineCmd] = useState('');
  const [refining, setRefining] = useState(false);
  const [dragOverBlock, setDragOverBlock] = useState<string | null>(null);
  const [showMemoriesDrawer, setShowMemoriesDrawer] = useState(false);

  const handleRefine = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!refineCmd.trim() || refining) return;
    setRefining(true);
    try {
      await onRefine(refineCmd.trim());
      setRefineCmd('');
    } finally {
      setRefining(false);
    }
  };

  const renderBlockContent = (blk: WorkspaceBlock) => {
    switch (blk.type) {
      case 'budget_sheet':
        return <BudgetBlock block={blk} onUpdate={(d, s) => onUpdateBlock(blk.id, d, s)} />;
      case 'map_weather':
        return <MapWeatherBlock block={blk} />;
      case 'checklist_timeline':
        return <ChecklistBlock block={blk} onUpdate={(d, s) => onUpdateBlock(blk.id, d, s)} />;
      case 'doc_editor':
        return <DocEditorBlock block={blk} onUpdate={(d, s) => onUpdateBlock(blk.id, d, s)} />;
      case 'semantic_viewer':
        return <SemanticViewerBlock block={blk} />;
      case 'focus_timer':
        return <FocusTimerBlock block={blk} />;
      default:
        return (
          <pre className="text-xs font-mono text-slate-300 overflow-x-auto">
            {JSON.stringify(blk.data, null, 2)}
          </pre>
        );
    }
  };

  const colSpanClass = (span: number) => {
    if (span >= 12) return 'lg:col-span-12';
    if (span >= 8) return 'lg:col-span-8';
    if (span >= 7) return 'lg:col-span-7';
    if (span >= 6) return 'lg:col-span-6';
    if (span >= 5) return 'lg:col-span-5';
    return 'lg:col-span-4';
  };

  return (
    <div className={`max-w-7xl mx-auto px-4 pt-4 pb-24 ${lens === 'xray' ? 'xray-grid' : ''}`}>
      {/* Workspace Header + Cognitive Lens Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div className="flex items-center gap-3">
          <button
            onClick={onBackHome}
            className="p-2 rounded-xl glass-panel hover:border-cyan-400/50 text-slate-300"
            title="Voltar ao Horizonte"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg sm:text-xl font-semibold text-white">{workspace.title}</h2>
              <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300">
                v{workspace.version}
              </span>
            </div>
            <p className="text-xs text-slate-400">{workspace.essence.headline}</p>
          </div>
        </div>

        {/* 3 Cognitive Lenses */}
        <div className="flex items-center gap-2">
          <div className="glass-panel rounded-xl p-1 flex items-center gap-1">
            {([
              { id: 'essence', label: 'Essência', icon: Sparkles },
              { id: 'work', label: 'Trabalho', icon: Layers },
              { id: 'xray', label: 'Raio-X', icon: Eye },
            ] as const).map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => onLensChange(id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
                  lens === id
                    ? 'bg-cyan-500 text-slate-950 shadow'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800/70'
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
              </button>
            ))}
          </div>

          <button
            onClick={() => setShowMemoriesDrawer((v) => !v)}
            className={`px-3 py-2 rounded-xl text-xs font-medium flex items-center gap-1.5 border transition-all ${
              showMemoriesDrawer
                ? 'bg-indigo-500/20 border-indigo-400/60 text-indigo-200'
                : 'glass-panel text-slate-300 hover:border-indigo-400/50'
            }`}
            title="Arraste memórias sobre blocos (Física de Intenção)"
          >
            <Magnet className="w-3.5 h-3.5 text-indigo-400" />
            <span className="hidden sm:inline">Física de Intenção</span>
          </button>

          <button
            onClick={onDissolve}
            className="px-3 py-2 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-300 hover:bg-rose-500/25 text-xs font-medium flex items-center gap-1.5"
            title="Arquiva o contexto no SemanticFS e dissolve esta interface efêmera"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Concluir &amp; Dissolver</span>
          </button>
        </div>
      </div>

      {/* Intent Physics Draggable Memory Strip */}
      {showMemoriesDrawer && (
        <div className="glass-panel rounded-2xl p-3.5 mb-5 border-indigo-500/30">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-indigo-300 flex items-center gap-1.5">
              <Magnet className="w-3.5 h-3.5" />
              Arraste qualquer memória abaixo e solte sobre a Planilha, Editor ou Cronograma para fundir automaticamente
            </span>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {memories.slice(0, 8).map((m) => (
              <div
                key={m.id}
                draggable
                onDragStart={(e) => e.dataTransfer.setData('text/newera-semantic-id', m.id)}
                className="shrink-0 w-56 rounded-xl bg-slate-900/90 border border-slate-700 hover:border-indigo-400 p-2.5 cursor-grab active:cursor-grabbing"
              >
                <div className="text-xs font-medium text-slate-100 truncate">{m.title}</div>
                <div className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">{m.summary}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* LENS 1: ESSENCE (Pure Focus & Decisions) */}
      {lens === 'essence' && (
        <div className="max-w-3xl mx-auto glass-panel rounded-3xl p-8 space-y-6">
          <div className="inline-flex items-center gap-2 text-xs text-cyan-300 bg-cyan-500/10 px-3 py-1 rounded-full">
            <Sparkles className="w-3.5 h-3.5" /> Camada Essência · Foco em Decisão
          </div>
          <h3 className="text-2xl sm:text-3xl font-light text-white leading-snug">
            {workspace.essence.headline}
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {workspace.essence.metrics.map((m) => (
              <div
                key={m.label}
                className="rounded-2xl bg-slate-900/80 border border-slate-800 p-4"
              >
                <div className="text-xs text-slate-400">{m.label}</div>
                <div
                  className={`text-lg font-semibold mt-1 ${
                    m.status === 'alert'
                      ? 'text-rose-400'
                      : m.status === 'ok'
                      ? 'text-emerald-400'
                      : 'text-cyan-300'
                  }`}
                >
                  {m.value}
                </div>
              </div>
            ))}
          </div>
          <div className="space-y-2 pt-2">
            <div className="text-xs uppercase tracking-wider text-slate-500">Próximas Ações Sugeridas</div>
            {workspace.essence.next_actions.map((act) => (
              <div key={act} className="flex items-center gap-2 text-sm text-slate-300">
                <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0" />
                <span>{act}</span>
              </div>
            ))}
          </div>
          <button
            onClick={() => onLensChange('work')}
            className="px-4 py-2 rounded-xl bg-cyan-500 text-slate-950 font-semibold text-xs hover:brightness-110"
          >
            Abrir Blocos de Trabalho →
          </button>
        </div>
      )}

      {/* LENS 3 BANNER: X-RAY (Data Wires & Semantic Transparency) */}
      {lens === 'xray' && (
        <div className="glass-panel rounded-2xl p-4 mb-5 border-cyan-400/40 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-cyan-300 flex items-center gap-2">
              <GitBranch className="w-4 h-4" />
              CAMADA RAIO-X · Fios Reativos de Dados &amp; Transparência do Núcleo
            </span>
            <span className="text-[11px] font-mono text-slate-400">
              Pressione Alt+X para o Inspetor Dev Completo
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {workspace.wires.map((w) => (
              <div
                key={w.id}
                className="rounded-xl bg-cyan-950/30 border border-cyan-500/30 p-2.5 text-xs font-mono"
              >
                <div className="text-cyan-300">
                  {w.from_block}.{w.from_field} ──▶ {w.to_block}.{w.to_field}
                </div>
                <div className="text-slate-400 font-sans text-[11px] mt-0.5">{w.label}</div>
              </div>
            ))}
            {workspace.wires.length === 0 && (
              <div className="text-xs text-slate-400">Nenhum fio entre blocos neste workspace simples.</div>
            )}
          </div>
        </div>
      )}

      {/* LENS 2 & 3: LIVE GENERATIVE BLOCKS GRID */}
      {lens !== 'essence' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 mb-6">
          {workspace.blocks.map((blk) => {
            const isOver = dragOverBlock === blk.id;
            return (
              <div
                key={blk.id}
                onDragOver={(e) => {
                  if (blk.accepts_drop && blk.accepts_drop.length > 0) {
                    e.preventDefault();
                    setDragOverBlock(blk.id);
                  }
                }}
                onDragLeave={() => setDragOverBlock(null)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOverBlock(null);
                  const semId = e.dataTransfer.getData('text/newera-semantic-id');
                  if (semId) {
                    onPhysicsMerge(blk.id, semId);
                  }
                }}
                className={`${colSpanClass(blk.col_span)} glass-panel rounded-2xl p-4 sm:p-5 transition-all ${
                  isOver
                    ? 'border-indigo-400 ring-2 ring-indigo-400/40 scale-[1.01]'
                    : lens === 'xray'
                    ? 'border-cyan-500/40'
                    : ''
                }`}
              >
                <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-800/80">
                  <div>
                    <h3 className="text-sm font-semibold text-white">{blk.title}</h3>
                    {lens === 'xray' && (
                      <div className="text-[10px] font-mono text-cyan-400 flex items-center gap-1 mt-0.5">
                        <Cpu className="w-3 h-3" /> {blk.capability} · id={blk.id}
                      </div>
                    )}
                  </div>
                  {blk.accepts_drop && blk.accepts_drop.length > 0 && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300">
                      Aceita fusão
                    </span>
                  )}
                </div>
                {renderBlockContent(blk)}
              </div>
            );
          })}
        </div>
      )}

      {/* TIME-TRAVEL SCRUBBER + CONTINUOUS REFINEMENT BAR */}
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 w-[95%] max-w-4xl z-30 space-y-2">
        {workspace.history.length > 1 && (
          <div className="glass-panel rounded-xl px-3 py-1.5 flex items-center gap-2 overflow-x-auto text-[11px]">
            <span className="text-slate-400 flex items-center gap-1 shrink-0">
              <History className="w-3.5 h-3.5 text-cyan-400" /> Time-Travel:
            </span>
            {workspace.history.map((snap) => (
              <button
                key={snap.version}
                onClick={() => onRestoreVersion(snap.version)}
                title={snap.summary}
                className={`px-2 py-0.5 rounded-md font-mono shrink-0 transition-colors ${
                  snap.version === workspace.version
                    ? 'bg-cyan-500 text-slate-950 font-semibold'
                    : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                }`}
              >
                v{snap.version}
              </button>
            ))}
          </div>
        )}

        <form
          onSubmit={handleRefine}
          className="glass-panel rounded-2xl p-2 flex items-center gap-2 shadow-2xl border-cyan-500/30"
        >
          <Sparkles className="w-4 h-4 text-cyan-400 ml-2 shrink-0" />
          <input
            type="text"
            value={refineCmd}
            onChange={(e) => setRefineCmd(e.target.value)}
            placeholder="Refinar esta tela ao vivo (ex: 'reduza o orçamento para R$ 3.200', 'adicione checklist de mala', 'adicione modo foco')..."
            className="flex-1 bg-transparent text-xs sm:text-sm text-slate-100 placeholder-slate-500 outline-none py-1.5"
            disabled={refining}
          />
          <button
            type="submit"
            disabled={refining || !refineCmd.trim()}
            className="px-3.5 py-1.5 rounded-xl bg-cyan-500 text-slate-950 font-semibold text-xs flex items-center gap-1 hover:brightness-110 disabled:opacity-40"
          >
            <Send className="w-3.5 h-3.5" />
            {refining ? '...' : 'Refinar'}
          </button>
        </form>
      </div>
    </div>
  );
};
