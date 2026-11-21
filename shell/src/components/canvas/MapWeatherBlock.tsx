import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import { CloudSun, MapPin } from 'lucide-react';
import type { WorkspaceBlock } from '../../types';

interface Props {
  block: WorkspaceBlock;
}

export const MapWeatherBlock: React.FC<Props> = ({ block }) => {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const leafletMap = useRef<L.Map | null>(null);

  const lat = Number(block.data.lat || -27.5954);
  const lon = Number(block.data.lon || -48.548);
  const markers: Array<{ name: string; lat: number; lon: number }> = block.data.markers || [];
  const forecast: Array<{
    date: string;
    condition: string;
    temp_max: number;
    temp_min: number;
    rain_prob: number;
  }> = block.data.forecast || [];

  useEffect(() => {
    if (!mapRef.current) return;
    if (leafletMap.current) {
      leafletMap.current.remove();
      leafletMap.current = null;
    }

    const map = L.map(mapRef.current, { zoomControl: false }).setView([lat, lon], 12);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap',
    }).addTo(map);

    markers.forEach((m) => {
      L.circleMarker([m.lat, m.lon], {
        radius: 8,
        color: '#22d3ee',
        fillColor: '#06b6d4',
        fillOpacity: 0.75,
      })
        .bindPopup(m.name)
        .addTo(map);
    });

    leafletMap.current = map;
    return () => {
      map.remove();
      leafletMap.current = null;
    };
  }, [lat, lon, markers.length]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span className="inline-flex items-center gap-1.5 text-slate-200 font-medium">
          <MapPin className="w-3.5 h-3.5 text-cyan-400" />
          {block.data.destination}
        </span>
        <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-cyan-300">
          {block.data.live_weather ? 'Clima ao vivo (Open-Meteo)' : 'Modo offline'}
        </span>
      </div>

      <div ref={mapRef} className="h-48 w-full rounded-xl overflow-hidden border border-slate-800" />

      {/* Forecast strip */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
          <CloudSun className="w-3.5 h-3.5 text-amber-300" />
          <span>Previsão para o período</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {forecast.slice(0, 6).map((f) => (
            <div
              key={f.date}
              className="rounded-lg bg-slate-900/75 border border-slate-800 p-2 text-[11px]"
            >
              <div className="text-slate-400 font-mono text-[10px]">{f.date}</div>
              <div className="text-slate-100 font-medium truncate">{f.condition}</div>
              <div className="text-cyan-300 mt-0.5">
                {f.temp_max}° / <span className="text-slate-400">{f.temp_min}°</span> · 💧{f.rain_prob}%
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
