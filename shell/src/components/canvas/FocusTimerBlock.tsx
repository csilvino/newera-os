import React, { useEffect, useState } from 'react';
import { Pause, Play, RotateCcw, Sparkles } from 'lucide-react';
import type { WorkspaceBlock } from '../../types';

interface Props {
  block: WorkspaceBlock;
}

export const FocusTimerBlock: React.FC<Props> = ({ block }) => {
  const initialSec = Number(block.data.duration_minutes || 25) * 60;
  const [secondsLeft, setSecondsLeft] = useState(initialSec);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => {
      setSecondsLeft((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  const mins = String(Math.floor(secondsLeft / 60)).padStart(2, '0');
  const secs = String(secondsLeft % 60).padStart(2, '0');
  const pct = Math.round(((initialSec - secondsLeft) / Math.max(initialSec, 1)) * 100);

  return (
    <div className="flex flex-col items-center py-4 space-y-4">
      <div className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-full bg-indigo-500/20 text-indigo-300">
        <Sparkles className="w-3 h-3" /> Capacidade Contrib Auto-Descoberta
      </div>
      <div className="text-5xl font-mono font-semibold tracking-wider text-white">
        {mins}:{secs}
      </div>
      <div className="w-full max-w-xs h-2 bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-cyan-400 to-indigo-400 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-slate-400 text-center max-w-xs">{block.data.goal}</p>
      <div className="flex gap-2">
        <button
          onClick={() => setRunning((r) => !r)}
          className="px-4 py-2 rounded-xl bg-cyan-500 text-slate-950 font-semibold text-xs flex items-center gap-1.5 hover:brightness-110"
        >
          {running ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          {running ? 'Pausar' : 'Iniciar Foco'}
        </button>
        <button
          onClick={() => {
            setRunning(false);
            setSecondsLeft(initialSec);
          }}
          className="px-3 py-2 rounded-xl bg-slate-800 text-slate-300 hover:bg-slate-700 text-xs flex items-center gap-1"
        >
          <RotateCcw className="w-3.5 h-3.5" /> Resetar
        </button>
      </div>
    </div>
  );
};
