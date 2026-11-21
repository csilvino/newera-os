import React, { useState } from 'react';
import { CheckCircle2, Circle, Plus } from 'lucide-react';
import type { WorkspaceBlock } from '../../types';

interface Props {
  block: WorkspaceBlock;
  onUpdate: (newData: Record<string, any>, summary: string) => void;
}

export const ChecklistBlock: React.FC<Props> = ({ block, onUpdate }) => {
  const items: Array<{ id: string; day: string; title: string; done: boolean }> =
    block.data.items || [];
  const [newTitle, setNewTitle] = useState('');

  const toggle = (id: string) => {
    const updated = items.map((it) => (it.id === id ? { ...it, done: !it.done } : it));
    onUpdate({ ...block.data, items: updated }, 'Progresso atualizado no cronograma');
  };

  const add = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    const updated = [
      ...items,
      { id: `t_${Date.now()}`, day: `Etapa ${items.length + 1}`, title: newTitle.trim(), done: false },
    ];
    setNewTitle('');
    onUpdate({ ...block.data, items: updated }, `Etapa adicionada: ${newTitle.trim()}`);
  };

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {items.map((it) => (
          <button
            key={it.id}
            onClick={() => toggle(it.id)}
            className={`w-full flex items-center gap-3 p-2.5 rounded-xl border text-left transition-all ${
              it.done
                ? 'bg-emerald-950/20 border-emerald-500/30 text-slate-400 line-through'
                : 'bg-slate-900/60 border-slate-800 hover:border-cyan-500/40 text-slate-200'
            }`}
          >
            {it.done ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <Circle className="w-4 h-4 text-slate-500 shrink-0" />
            )}
            <span className="text-[11px] font-mono text-cyan-400 shrink-0 w-16">{it.day}</span>
            <span className="text-xs flex-1">{it.title}</span>
          </button>
        ))}
      </div>

      <form onSubmit={add} className="flex gap-2">
        <input
          type="text"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="Adicionar nova etapa..."
          className="flex-1 bg-slate-900/80 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-cyan-400"
        />
        <button
          type="submit"
          className="px-3 py-1.5 rounded-lg bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 text-xs font-medium flex items-center gap-1"
        >
          <Plus className="w-3.5 h-3.5" /> Etapa
        </button>
      </form>
    </div>
  );
};
