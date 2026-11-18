import React, { useState } from 'react';
import { Shield, Zap, XCircle, TrendingUp, TrendingDown, AlertCircle } from 'lucide-react';
import { api } from '../services/api';

export default function ActivePositions({ positions, onUpdate }) {
  const [loadingTicket, setLoadingTicket] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);

  const handleBreakeven = async (ticket) => {
    setLoadingTicket(ticket);
    try {
      const res = await api.moveToBreakeven(ticket);
      setActionMessage({ type: 'success', text: res.message });
      setTimeout(() => setActionMessage(null), 4000);
      onUpdate();
    } catch (err) {
      setActionMessage({ type: 'error', text: err.message });
      setTimeout(() => setActionMessage(null), 5000);
    } finally {
      setLoadingTicket(null);
    }
  };

  const handleClose = async (ticket) => {
    if (!window.confirm(`Confirm emergency market close for Ticket #${ticket}?`)) return;
    setLoadingTicket(ticket);
    try {
      const res = await api.closeTrade(ticket);
      setActionMessage({ type: 'success', text: res.message });
      setTimeout(() => setActionMessage(null), 4000);
      onUpdate();
    } catch (err) {
      setActionMessage({ type: 'error', text: err.message });
      setTimeout(() => setActionMessage(null), 5000);
    } finally {
      setLoadingTicket(null);
    }
  };

  return (
    <div className="bg-[#111726] border border-[#1E293B] rounded-xl p-5 shadow-lg">
      <div className="flex items-center justify-between pb-4 border-b border-[#1E293B]">
        <div className="flex items-center space-x-2">
          <Shield className="h-5 w-5 text-cyan-400" />
          <h2 className="font-mono font-bold text-sm tracking-wide text-white uppercase">
            Active Institutional Positions
          </h2>
          <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-cyan-950/60 text-cyan-300 border border-cyan-800/40">
            {positions?.length ?? 0} OPEN
          </span>
        </div>

        {actionMessage && (
          <div
            className={`text-xs font-mono px-3 py-1 rounded border animate-fade-in ${
              actionMessage.type === 'success'
                ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300'
                : 'bg-rose-950/40 border-rose-800 text-rose-300'
            }`}
          >
            {actionMessage.text}
          </div>
        )}
      </div>

      <div className="overflow-x-auto pt-3">
        {(!positions || positions.length === 0) ? (
          <div className="py-10 text-center text-slate-500 font-mono text-xs">
            <AlertCircle className="h-8 w-8 mx-auto mb-2 text-slate-600 opacity-60" />
            <p>No open positions in MT5.</p>
            <p className="text-[11px] text-slate-600 mt-1">
              Autonomous scalper daemon is continuously scanning 5 pairs for high-probability setups.
            </p>
          </div>
        ) : (
          <table className="w-full text-left font-mono text-xs">
            <thead>
              <tr className="border-b border-[#1E293B] text-[10px] text-slate-400 uppercase tracking-wider">
                <th className="pb-2.5">Ticket</th>
                <th className="pb-2.5">Symbol</th>
                <th className="pb-2.5">Side</th>
                <th className="pb-2.5">Lots</th>
                <th className="pb-2.5">Entry</th>
                <th className="pb-2.5">Current</th>
                <th className="pb-2.5">Stop Loss</th>
                <th className="pb-2.5">Target TP</th>
                <th className="pb-2.5">Floating P&L</th>
                <th className="pb-2.5">Status</th>
                <th className="pb-2.5 text-right">Risk Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1A2338]">
              {positions.map((pos) => {
                const isBuy = pos.direction === 'BUY';
                const pnl = pos.floating_profit ?? 0;
                const isProfit = pnl >= 0;

                return (
                  <tr key={pos.id} className="hover:bg-[#141C2E] transition-colors">
                    <td className="py-3 text-slate-300 font-medium">#{pos.mt5_ticket}</td>
                    <td className="py-3 font-semibold text-slate-100">{pos.symbol}</td>
                    <td className="py-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          isBuy
                            ? 'bg-emerald-950/60 text-emerald-400 border border-emerald-800/40'
                            : 'bg-rose-950/60 text-rose-400 border border-rose-800/40'
                        }`}
                      >
                        {pos.direction}
                      </span>
                    </td>
                    <td className="py-3 text-slate-300">{pos.lot_size.toFixed(2)}</td>
                    <td className="py-3 text-slate-300">{pos.entry_price}</td>
                    <td className="py-3 font-semibold text-slate-100">{pos.current_price}</td>
                    <td className="py-3 text-rose-300">{pos.stop_loss || '—'}</td>
                    <td className="py-3 text-emerald-300">{pos.take_profit || '—'}</td>
                    <td className="py-3">
                      <div className="flex items-center space-x-1 font-bold">
                        {isProfit ? (
                          <span className="text-emerald-400">+${pnl.toFixed(2)}</span>
                        ) : (
                          <span className="text-rose-400">-${Math.abs(pnl).toFixed(2)}</span>
                        )}
                        {pos.r_multiple !== undefined && (
                          <span
                            className={`text-[10px] px-1 py-0.2 rounded font-normal ${
                              pos.r_multiple > 0
                                ? 'bg-emerald-900/40 text-emerald-300'
                                : 'bg-rose-900/40 text-rose-300'
                            }`}
                          >
                            {pos.r_multiple > 0 ? '+' : ''}{pos.r_multiple}R
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3">
                      {pos.is_breakeven ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-800">
                          <Shield className="h-2.5 w-2.5 mr-1" />
                          RISK FREE
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-amber-950/60 text-amber-300 border border-amber-800/50">
                          AT RISK (1.0R)
                        </span>
                      )}
                    </td>
                    <td className="py-3 text-right">
                      <div className="flex items-center justify-end space-x-2">
                        {!pos.is_breakeven && (
                          <button
                            onClick={() => handleBreakeven(pos.mt5_ticket)}
                            disabled={loadingTicket === pos.mt5_ticket}
                            className="px-2.5 py-1 text-[11px] rounded bg-cyan-950/70 border border-cyan-800/60 text-cyan-300 hover:bg-cyan-900 transition-colors flex items-center space-x-1"
                            title="Move Stop Loss to Entry (+1R Trigger)"
                          >
                            <Zap className="h-3 w-3" />
                            <span>BE</span>
                          </button>
                        )}
                        <button
                          onClick={() => handleClose(pos.mt5_ticket)}
                          disabled={loadingTicket === pos.mt5_ticket}
                          className="px-2.5 py-1 text-[11px] rounded bg-rose-950/60 border border-rose-800/60 text-rose-300 hover:bg-rose-900 transition-colors flex items-center space-x-1"
                          title="Emergency Close Position"
                        >
                          <XCircle className="h-3 w-3" />
                          <span>Close</span>
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
