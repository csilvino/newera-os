import React, { useState } from 'react';
import { Plus, Trash2, TrendingUp } from 'lucide-react';
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { WorkspaceBlock } from '../../types';

interface Props {
  block: WorkspaceBlock;
  onUpdate: (newData: Record<string, any>, summary: string) => void;
}

const fmtBRL = (v: number) =>
  v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

export const BudgetBlock: React.FC<Props> = ({ block, onUpdate }) => {
  const rows: any[] = block.data.rows || [];
  const budgetLimit: number = Number(block.data.budget_limit || 4000);
  const summary = block.data.summary || { total: 0, remaining: budgetLimit, utilization_pct: 0, chart: [] };

  const [newItem, setNewItem] = useState('');
  const [newCost, setNewCost] = useState('');

  const updateRowCost = (id: string, value: number) => {
    const updated = rows.map((r) => (r.id === id ? { ...r, cost: value } : r));
    onUpdate({ ...block.data, rows: updated }, 'Valor atualizado na planilha de custos');
  };

  const removeRow = (id: string) => {
    const updated = rows.filter((r) => r.id !== id);
    onUpdate({ ...block.data, rows: updated }, 'Linha removida da planilha');
  };

  const addRow = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newItem.trim()) return;
    const cost = parseFloat(newCost.replace(',', '.')) || 0;
    const updated = [
      ...rows,
      { id: `r_${Date.now()}`, category: 'Personalizado', item: newItem.trim(), qty: 1, cost },
    ];
    setNewItem('');
    setNewCost('');
    onUpdate({ ...block.data, rows: updated }, `Item '${newItem.trim()}' adicionado ao orçamento`);
  };

  const overBudget = summary.remaining < 0;

  return (
    <div className="space-y-4">
      {/* Live KPI strip */}
      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-xl bg-slate-900/70 p-3 border border-slate-800">
          <div className="text-[11px] text-slate-400">Total Previsto</div>
          <div className="text-base font-semibold text-white">{fmtBRL(summary.total || 0)}</div>
        </div>
        <div className="rounded-xl bg-slate-900/70 p-3 border border-slate-800">
          <div className="text-[11px] text-slate-400">Teto Definido</div>
          <div className="text-base font-semibold text-cyan-300">{fmtBRL(budgetLimit)}</div>
        </div>
        <div
          className={`rounded-xl p-3 border ${
            overBudget
              ? 'bg-rose-950/40 border-rose-500/40 text-rose-300'
              : 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300'
          }`}
        >
          <div className="text-[11px] opacity-80">{overBudget ? 'Excedente' : 'Saldo Livre'}</div>
          <div className="text-base font-semibold">{fmtBRL(Math.abs(summary.remaining || 0))}</div>
        </div>
      </div>

      {/* Editable table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-400 border-b border-slate-800">
              <th className="text-left py-2 font-medium">Item</th>
              <th className="text-left py-2 font-medium">Cat.</th>
              <th className="text-right py-2 font-medium">Qtd</th>
              <th className="text-right py-2 font-medium">Unitário (R$)</th>
              <th className="w-7"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {rows.map((r) => (
              <tr key={r.id} className="hover:bg-slate-800/30">
                <td className="py-2 pr-2 text-slate-200">{r.item}</td>
                <td className="py-2 pr-2">
                  <span className="px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 text-[10px]">
                    {r.category}
                  </span>
                </td>
                <td className="py-2 text-right text-slate-400">{r.qty}</td>
                <td className="py-2 text-right">
                  <input
                    type="number"
                    step="10"
                    defaultValue={r.cost}
                    onBlur={(e) => updateRowCost(r.id, parseFloat(e.target.value) || 0)}
                    className="w-24 text-right bg-slate-900 border border-slate-700 rounded-md px-2 py-1 text-slate-100 focus:border-cyan-400 outline-none"
                  />
                </td>
                <td className="py-2 text-right">
                  <button
                    onClick={() => removeRow(r.id)}
                    className="text-slate-500 hover:text-rose-400 p-1"
                    title="Remover linha"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Add row */}
      <form onSubmit={addRow} className="flex gap-2">
        <input
          type="text"
          value={newItem}
          onChange={(e) => setNewItem(e.target.value)}
          placeholder="Adicionar custo..."
          className="flex-1 bg-slate-900/80 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-cyan-400"
        />
        <input
          type="number"
          value={newCost}
          onChange={(e) => setNewCost(e.target.value)}
          placeholder="R$"
          className="w-24 bg-slate-900/80 border border-slate-700 rounded-lg px-2 py-1.5 text-xs text-slate-100 outline-none focus:border-cyan-400"
        />
        <button
          type="submit"
          className="px-3 py-1.5 rounded-lg bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 text-xs font-medium flex items-center gap-1"
        >
          <Plus className="w-3.5 h-3.5" /> Incluir
        </button>
      </form>

      {/* Distribution chart */}
      {summary.chart && summary.chart.length > 0 && (
        <div className="pt-2 border-t border-slate-800/80">
          <div className="flex items-center gap-1.5 text-[11px] text-slate-400 mb-2">
            <TrendingUp className="w-3.5 h-3.5 text-cyan-400" />
            <span>Distribuição por Categoria</span>
          </div>
          <div className="h-32 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={summary.chart}>
                <XAxis dataKey="category" tick={{ fill: '#94a3b8', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis hide />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                  formatter={(v: any) => fmtBRL(Number(v))}
                />
                <Bar dataKey="amount" fill="#22d3ee" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
};
