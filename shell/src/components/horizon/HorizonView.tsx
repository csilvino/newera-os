import React, { useState } from 'react';
import {
  ArrowRight,
  Clock,
  Mic,
  MicOff,
  ShieldCheck,
  Sparkles,
  Workflow,
} from 'lucide-react';
import type { SystemStatus } from '../../types';

interface Props {
  status: SystemStatus | null;
  loading: boolean;
  onSubmitIntent: (query: string) => void;
  onOpenWorkspace: (id: string) => void;
}

const STARTER_INTENTS = [
  {
    label: 'Viagem + Orçamento + Mapa',
    query: 'Planejar uma viagem de 5 dias para Florianópolis com orçamento de R$ 4.000',
    tag: 'Interface Generativa',
  },
  {
    label: 'Busca Semântica sem Pastas',
    query: 'Mostre aquele contrato em PDF que revisei semana passada com o João',
    tag: 'SemanticFS',
  },
  {
    label: 'Sessão de Foco (SDK Contrib)',
    query: 'Quero entrar em modo foco pomodoro de 25 minutos para estudar arquitetura',
    tag: 'Contrib SDK',
  },
  {
    label: 'Orçamento Dinâmico',
    query: 'Criar orçamento mensal de R$ 6.500 com divisão de custos',
    tag: 'Motor de Cálculo',
  },
];

export const HorizonView: React.FC<Props> = ({
  status,
  loading,
  onSubmitIntent,
  onOpenWorkspace,
}) => {
  const [query, setQuery] = useState('');
  const [listening, setListening] = useState(false);

  const toggleVoice = () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('Reconhecimento de voz não suportado neste navegador. Use Chrome ou Edge.');
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = 'pt-BR';
    recognition.interimResults = false;
    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognition.onresult = (event: any) => {
      const transcript = event.results[0][0].transcript;
      setQuery(transcript);
      onSubmitIntent(transcript);
    };
    recognition.start();
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || loading) return;
    onSubmitIntent(query.trim());
  };

  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Bom dia' : hour < 18 ? 'Boa tarde' : 'Boa noite';

  return (
    <div className="max-w-4xl mx-auto px-4 pt-12 pb-20 flex flex-col items-center">
      {/* Identity Pill */}
      <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full glass-panel text-xs text-cyan-300 mb-6">
        <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
        <span>
          Identidade Soberana:{' '}
          <span className="font-mono text-slate-200">
            {status?.guardian.identity.fingerprint || 'LOCAL'}
          </span>
        </span>
        <span className="text-slate-600">•</span>
        <span className="text-slate-400">
          {status?.capabilities.length || 5} capacidades ativas
        </span>
      </div>

      {/* Main Heading */}
      <h1 className="text-3xl sm:text-5xl font-light tracking-tight text-center text-white mb-3">
        {greeting}. <span className="text-cyan-400 font-normal">Qual é a sua intenção?</span>
      </h1>
      <p className="text-slate-400 text-center max-w-xl text-sm sm:text-base mb-10">
        Sem janelas, sem pastas e sem abrir aplicativos separados. Descreva o que você precisa
        e o <strong className="text-slate-200">Newera OS</strong> monta o ambiente exato em tempo real.
      </p>

      {/* Intent Bar */}
      <form onSubmit={handleSubmit} className="w-full max-w-2xl mb-8">
        <div className="glass-panel rounded-2xl p-2 flex items-center gap-2 focus-within:border-cyan-400/60 focus-within:shadow-[0_0_32px_-8px_rgba(34,211,238,0.45)] transition-all">
          <div className="pl-3 text-cyan-400">
            <Sparkles className="w-5 h-5" />
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ex: Planejar viagem de 5 dias com R$ 4.000 ou buscar contrato com o João..."
            className="flex-1 bg-transparent border-none outline-none text-slate-100 placeholder-slate-500 text-sm sm:text-base py-2.5"
            disabled={loading}
          />
          <button
            type="button"
            onClick={toggleVoice}
            title="Falar intenção (PT-BR)"
            className={`p-2.5 rounded-xl transition-colors ${
              listening
                ? 'bg-rose-500/20 text-rose-400 animate-pulse'
                : 'text-slate-400 hover:text-cyan-300 hover:bg-slate-800/70'
            }`}
          >
            {listening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
          </button>
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-indigo-500 text-slate-950 font-semibold text-sm flex items-center gap-1.5 hover:brightness-110 disabled:opacity-40 transition-all"
          >
            {loading ? 'Compondo...' : 'Gerar'}
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </form>

      {/* Starter Intents */}
      <div className="w-full max-w-3xl grid grid-cols-1 sm:grid-cols-2 gap-3 mb-12">
        {STARTER_INTENTS.map((item) => (
          <button
            key={item.label}
            onClick={() => onSubmitIntent(item.query)}
            disabled={loading}
            className="glass-panel glass-panel-hover rounded-xl p-4 text-left transition-all group"
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-cyan-400">{item.label}</span>
              <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
                {item.tag}
              </span>
            </div>
            <p className="text-xs text-slate-400 group-hover:text-slate-200 line-clamp-2">
              “{item.query}”
            </p>
          </button>
        ))}
      </div>

      {/* Active Contexts */}
      {status && status.active_workspaces.length > 0 && (
        <div className="w-full max-w-3xl">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-slate-400 mb-3">
            <Workflow className="w-3.5 h-3.5 text-cyan-400" />
            <span>Contextos Vivos (retomar instantaneamente)</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {status.active_workspaces.map((ws) => (
              <button
                key={ws.id}
                onClick={() => onOpenWorkspace(ws.id)}
                className="glass-panel glass-panel-hover rounded-xl p-4 text-left transition-all"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium text-sm text-slate-100 truncate">{ws.title}</span>
                  <span className="text-[11px] font-mono text-cyan-400">v{ws.version}</span>
                </div>
                <p className="text-xs text-slate-400 line-clamp-1 mb-2">{ws.headline}</p>
                <div className="flex items-center gap-2 text-[11px] text-slate-500">
                  <Clock className="w-3 h-3" />
                  <span>{ws.blocks_count} blocos conectados</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
