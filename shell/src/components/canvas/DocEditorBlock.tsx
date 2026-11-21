import React, { useEffect, useState } from 'react';
import { Download, Save } from 'lucide-react';
import type { WorkspaceBlock } from '../../types';

interface Props {
  block: WorkspaceBlock;
  onUpdate: (newData: Record<string, any>, summary: string) => void;
}

export const DocEditorBlock: React.FC<Props> = ({ block, onUpdate }) => {
  const [text, setText] = useState(block.data.markdown || '');

  useEffect(() => {
    setText(block.data.markdown || '');
  }, [block.data.markdown]);

  const exportMd = () => {
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${block.title.toLowerCase().replace(/\s+/g, '_')}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={10}
        className="w-full bg-slate-950/70 border border-slate-800 rounded-xl p-3 text-xs sm:text-sm font-mono text-slate-200 leading-relaxed outline-none focus:border-cyan-400/60 resize-y"
      />
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-slate-500">
          Dica: arraste uma memória do SemanticFS sobre este bloco para fundir contexto.
        </span>
        <div className="flex gap-2">
          <button
            onClick={exportMd}
            className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs flex items-center gap-1"
          >
            <Download className="w-3.5 h-3.5" /> Exportar .md
          </button>
          <button
            onClick={() => onUpdate({ ...block.data, markdown: text }, 'Documento salvo no contexto ativo')}
            className="px-3 py-1 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 text-xs font-medium flex items-center gap-1"
          >
            <Save className="w-3.5 h-3.5" /> Salvar estado
          </button>
        </div>
      </div>
    </div>
  );
};
