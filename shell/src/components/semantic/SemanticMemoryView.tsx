import React, { useEffect, useState } from 'react';
import { FileUp, Network, Plus, Search, Sparkles, Tag, Users } from 'lucide-react';
import { api } from '../../services/api';
import type { SemanticGraphData, SemanticObject } from '../../types';

interface Props {
  onOpenInWorkspace: (query: string) => void;
}

export const SemanticMemoryView: React.FC<Props> = ({ onOpenInWorkspace }) => {
  const [objects, setObjects] = useState<SemanticObject[]>([]);
  const [graph, setGraph] = useState<SemanticGraphData | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [uploading, setUploading] = useState(false);

  const [noteTitle, setNoteTitle] = useState('');
  const [noteContent, setNoteContent] = useState('');
  const [notePeople, setNotePeople] = useState('');

  const loadAll = async () => {
    const [objs, g] = await Promise.all([api.listSemantic(), api.getSemanticGraph()]);
    setObjects(objs);
    setGraph(g);
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      await loadAll();
      return;
    }
    const res = await api.searchSemantic(searchQuery.trim());
    setObjects(res);
  };

  const handleFileUpload = async (file: File) => {
    setUploading(true);
    try {
      await api.uploadFile(file);
      await loadAll();
    } finally {
      setUploading(false);
    }
  };

  const handleCreateNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!noteTitle.trim() || !noteContent.trim()) return;
    const people = notePeople
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    await api.ingestNote(noteTitle.trim(), noteContent.trim(), [], people);
    setNoteTitle('');
    setNoteContent('');
    setNotePeople('');
    await loadAll();
  };

  // Compute circular layout for SVG semantic graph
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  const positions: Record<string, { x: number; y: number }> = {};
  nodes.forEach((n, idx) => {
    const angle = (idx / Math.max(nodes.length, 1)) * Math.PI * 2;
    const radius = n.kind === 'person' ? 85 : 155;
    positions[n.id] = {
      x: 240 + Math.cos(angle) * radius,
      y: 190 + Math.sin(angle) * radius,
    };
  });

  return (
    <div className="max-w-7xl mx-auto px-4 pt-6 pb-16 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Network className="w-5 h-5 text-cyan-400" />
            SemanticFS — Memória Semântica sem Pastas
          </h2>
          <p className="text-xs text-slate-400">
            Tudo é indexado por significado, contexto, tempo e pessoas. Nunca mais crie diretórios.
          </p>
        </div>

        {/* Folderless File Ingestion */}
        <label className="cursor-pointer px-4 py-2 rounded-xl bg-cyan-500/20 border border-cyan-500/40 text-cyan-200 hover:bg-cyan-500/30 text-xs font-medium flex items-center gap-2">
          <FileUp className="w-4 h-4" />
          {uploading ? 'Indexando...' : 'Ingerir Arquivo (PDF, TXT, CSV, MD)'}
          <input
            type="file"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFileUpload(f);
            }}
          />
        </label>
      </div>

      {/* Natural Language Search */}
      <form onSubmit={handleSearch} className="glass-panel rounded-2xl p-2 flex items-center gap-2">
        <Search className="w-4 h-4 text-cyan-400 ml-2" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Busque por contexto: 'contrato em PDF que revisei semana passada com o João'..."
          className="flex-1 bg-transparent text-sm text-slate-100 placeholder-slate-500 outline-none py-1.5"
        />
        <button
          type="submit"
          className="px-4 py-1.5 rounded-xl bg-cyan-500 text-slate-950 font-semibold text-xs"
        >
          Buscar por Significado
        </button>
      </form>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Interactive Semantic Graph SVG */}
        <div className="lg:col-span-5 glass-panel rounded-2xl p-4 space-y-3">
          <div className="text-xs font-semibold text-slate-200 flex items-center justify-between">
            <span>Mapa do Grafo Semântico</span>
            <span className="font-mono text-[11px] text-cyan-400">
              {nodes.length} nós · {edges.length} conexões
            </span>
          </div>
          <svg viewBox="0 0 480 380" className="w-full h-80 rounded-xl bg-slate-950/80 border border-slate-800">
            {edges.map((e, i) => {
              const p1 = positions[e.source];
              const p2 = positions[e.target];
              if (!p1 || !p2) return null;
              return (
                <line
                  key={i}
                  x1={p1.x}
                  y1={p1.y}
                  x2={p2.x}
                  y2={p2.y}
                  stroke={e.relation === 'mentions_person' ? '#818cf8' : '#22d3ee'}
                  strokeOpacity={0.35}
                  strokeWidth={1.5}
                />
              );
            })}
            {nodes.map((n) => {
              const p = positions[n.id];
              if (!p) return null;
              const isPerson = n.kind === 'person';
              return (
                <g key={n.id} transform={`translate(${p.x}, ${p.y})`}>
                  <circle
                    r={isPerson ? 15 : 11}
                    fill={isPerson ? '#4f46e5' : '#0891b2'}
                    stroke="#e2e8f0"
                    strokeWidth={1.2}
                  />
                  <text
                    y={isPerson ? 27 : 23}
                    textAnchor="middle"
                    fill="#cbd5e1"
                    fontSize="9"
                    className="select-none"
                  >
                    {n.label.slice(0, 20)}
                  </text>
                </g>
              );
            })}
          </svg>

          {/* Quick Semantic Note */}
          <form onSubmit={handleCreateNote} className="space-y-2 pt-2 border-t border-slate-800">
            <div className="text-xs font-medium text-slate-300 flex items-center gap-1.5">
              <Plus className="w-3.5 h-3.5 text-cyan-400" /> Registrar Memória Rápida
            </div>
            <input
              type="text"
              value={noteTitle}
              onChange={(e) => setNoteTitle(e.target.value)}
              placeholder="Título da memória ou nota..."
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-cyan-400"
            />
            <textarea
              value={noteContent}
              onChange={(e) => setNoteContent(e.target.value)}
              placeholder="Conteúdo (valores em R$, pessoas e tópicos são indexados automaticamente)..."
              rows={2}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-cyan-400"
            />
            <div className="flex gap-2">
              <input
                type="text"
                value={notePeople}
                onChange={(e) => setNotePeople(e.target.value)}
                placeholder="Pessoas (ex: João, Maria)"
                className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-cyan-400"
              />
              <button
                type="submit"
                className="px-3 py-1.5 rounded-lg bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 text-xs font-medium"
              >
                Indexar
              </button>
            </div>
          </form>
        </div>

        {/* Semantic Objects List */}
        <div className="lg:col-span-7 space-y-3">
          {objects.map((o) => (
            <div
              key={o.id}
              className="glass-panel glass-panel-hover rounded-2xl p-4 transition-all space-y-2"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-semibold text-white">{o.title}</h3>
                  <div className="text-[11px] font-mono text-slate-500">
                    hash:{o.content_hash.slice(0, 12)} · {o.kind}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {typeof o.score === 'number' && (
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300">
                      {Math.round(o.score * 100)}%
                    </span>
                  )}
                  <button
                    onClick={() => onOpenInWorkspace(`Mostre ${o.title}`)}
                    className="px-2.5 py-1 rounded-lg bg-cyan-500/15 text-cyan-300 hover:bg-cyan-500/25 text-xs flex items-center gap-1"
                  >
                    <Sparkles className="w-3 h-3" /> Abrir no Canvas
                  </button>
                </div>
              </div>
              <p className="text-xs text-slate-300">{o.summary}</p>
              <div className="flex flex-wrap gap-1.5 pt-1">
                {(o.entities?.people || []).map((p) => (
                  <span
                    key={p}
                    className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300"
                  >
                    <Users className="w-2.5 h-2.5" /> {p}
                  </span>
                ))}
                {o.tags.map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-300"
                  >
                    <Tag className="w-2.5 h-2.5" /> {t}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
