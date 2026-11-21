import React, { useEffect, useState } from 'react';
import { Laptop, Smartphone, Wifi, X } from 'lucide-react';
import { api } from '../../services/api';

interface Props {
  open: boolean;
  onClose: () => void;
  workspaceId?: string;
}

export const ContinuumModal: React.FC<Props> = ({ open, onClose, workspaceId }) => {
  const [info, setInfo] = useState<{
    lan_ip: string;
    url: string;
    qr_svg: string;
    connected_devices: Array<{ id: string; device_type: string; device_name: string }>;
  } | null>(null);

  useEffect(() => {
    if (!open) return;
    api.getHandoff(workspaceId).then(setInfo).catch(() => {});
  }, [open, workspaceId]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4">
      <div className="glass-panel rounded-2xl w-full max-w-md p-6 border-cyan-500/40 space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Wifi className="w-5 h-5 text-cyan-400" />
            <h3 className="text-base font-semibold text-white">Computação Contínua (Continuum)</h3>
          </div>
          <button onClick={onClose} className="p-1 text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-xs text-slate-300 leading-relaxed">
          Aponte a câmera do seu celular ou tablet (na mesma rede Wi-Fi) para continuar esta mesma
          sessão instantaneamente. O processamento pesado permanece no PC e a interface se adapta à tela.
        </p>

        {info && (
          <div className="flex flex-col items-center space-y-3">
            <div
              className="bg-white p-3 rounded-2xl w-48 h-48 flex items-center justify-center [&>svg]:w-full [&>svg]:h-full"
              dangerouslySetInnerHTML={{ __html: info.qr_svg }}
            />
            <div className="text-[11px] font-mono text-cyan-300 break-all text-center bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800 w-full">
              {info.url}
            </div>

            <div className="w-full pt-2 border-t border-slate-800 space-y-1.5">
              <div className="text-[11px] uppercase tracking-wider text-slate-500">
                Terminais Conectados ({info.connected_devices.length})
              </div>
              {info.connected_devices.map((d) => (
                <div
                  key={d.id}
                  className="flex items-center gap-2 text-xs text-slate-200 bg-slate-900/70 px-3 py-2 rounded-lg"
                >
                  {d.device_type === 'mobile' ? (
                    <Smartphone className="w-4 h-4 text-cyan-400" />
                  ) : (
                    <Laptop className="w-4 h-4 text-indigo-400" />
                  )}
                  <span>{d.device_name}</span>
                  <span className="ml-auto text-[10px] font-mono text-emerald-400">ONLINE</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
