import React from 'react';
import { FileText, Tag, Users } from 'lucide-react';
import type { WorkspaceBlock } from '../../types';

interface Props {
  block: WorkspaceBlock;
}

export const SemanticViewerBlock: React.FC<Props> = ({ block }) => {
  const d = block.data;
  const people: string[] = d.entities?.people || [];
  const tags: string[] = d.tags || [];
  const others: any[] = d.other_matches || [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-cyan-500/15 text-cyan-300">
          <FileText className="w-3.5 h-3.5" /> {d.original_name || d.kind}
        </span>
        {typeof d.score === 'number' && (
          <span className="px-2.5 py-1 rounded-full bg-emerald-500/15 text-emerald-300 font-mono">
            Relevância {Math.round(d.score * 100)}%
          </span>
        )}
        {people.map((p) => (
          <span key={p} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-indigo-500/20 text-indigo-300">
            <Users className="w-3 h-3" /> {p}
          </span>
        ))}
        {tags.map((t) => (
          <span key={t} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
            <Tag className="w-3 h-3" /> {t}
          </span>
        ))}
      </div>

      <div className="rounded-xl bg-slate-950/80 border border-slate-800 p-4 text-xs sm:text-sm text-slate-200 whitespace-pre-wrap leading-relaxed max-h-72 overflow-y-auto">
        {d.content_text}
      </div>

      {others.length > 0 && (
        <div>
          <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-2">
            Outras memórias relacionadas no grafo
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {others.map((o) => (
              <div key={o.id} className="rounded-lg bg-slate-900/60 border border-slate-800 p-2.5 text-xs">
                <div className="font-medium text-slate-200 truncate">{o.title}</div>
                <div className="text-slate-400 text-[11px] line-clamp-2 mt-0.5">{o.summary}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
