import React, { useState } from 'react';
import { BookOpen, CheckCircle, XCircle, ArrowRight } from 'lucide-react';

export default function TradeJournal({ trades, onRefresh }) {
  const [filterSymbol, setFilterSymbol] = useState('');

  const filtered = trades?.filter((t) => {
    if (!filterSymbol) return true;
    return t.symbol.toLowerCase().includes(filterSymbol.toLowerCase());
  }) || [];

  return (
    <div className="bg-[#111726] border border-[#1E293B] rounded-xl p-5 shadow-lg">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 pb-4 border-b border-[#1E293B]">
        <div className="flex items-center space-x-2">
          <BookOpen className="h-5 w-5 text-indigo-400" />
          <h2 className="font-mono font-bold text-sm tracking-wide text-white uppercase">
            Closed Trades Journal & Outcome Audit
          </h2>
        </div>

        <input
          type="text"
          placeholder="Filter by symbol (e.g. BTC)..."
          value={filterSymbol}
          onChange={(e) => setFilterSymbol(e.target.value)}
          className="bg-[#0B0E14] border border-[#1E293B] text-slate-200 text-xs font-mono px-3 py-1.5 rounded-lg focus:outline-none focus:border-cyan-500/50 w-full sm:w-56"
        />
      </div>

      <div className="overflow-x-auto pt-3">
        {filtered.length === 0 ? (
          <div className="py-8 text-center text-slate-500 font-mono text-xs">
            No closed trades matching filter.
          </div>
        ) : (
          <table className="w-full text-left font-mono text-xs">
            <thead>
              <tr className="border-b border-[#1E293B] text-[10px] text-slate-400 uppercase tracking-wider">
                <th className="pb-2.5">Ticket</th>
                <th className="pb-2.5">Symbol</th>
                <th className="pb-2.5">Side</th>
                <th className="pb-2.5">Lots</th>
                <th className="pb-2.5">Entry Price</th>
                <th className="pb-2.5">Exit Price</th>
                <th className="pb-2.5">Net Realized P&L</th>
                <th className="pb-2.5">Outcome Tag</th>
                <th className="pb-2.5">Close Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1A2338]">
              {filtered.map((t) => {
                const profit = t.profit ?? 0;
                const isWin = profit > 0;
                const isLoss = profit < 0;

                return (
                  <tr key={t.id} className="hover:bg-[#141C2E] transition-colors">
                    <td className="py-2.5 text-slate-400">#{t.mt5_ticket}</td>
                    <td className="py-2.5 font-bold text-slate-100">{t.symbol}</td>
                    <td className="py-2.5">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          t.direction === 'BUY'
                            ? 'bg-emerald-950/50 text-emerald-400'
                            : 'bg-rose-950/50 text-rose-400'
                        }`}
                      >
                        {t.direction}
                      </span>
                    </td>
                    <td className="py-2.5 text-slate-300">{t.lot_size.toFixed(2)}</td>
                    <td className="py-2.5 text-slate-300">{t.entry_price}</td>
                    <td className="py-2.5 text-slate-300">{t.exit_price || '—'}</td>
                    <td className="py-2.5 font-bold">
                      <span className={isWin ? 'text-emerald-400' : isLoss ? 'text-rose-400' : 'text-slate-400'}>
                        {isWin ? '+' : ''}${profit.toFixed(2)}
                      </span>
                    </td>
                    <td className="py-2.5">
                      {isWin ? (
                        <span className="inline-flex items-center text-[10px] px-2 py-0.5 rounded bg-emerald-950/70 border border-emerald-800 text-emerald-300 font-bold">
                          <CheckCircle className="h-2.5 w-2.5 mr-1" />
                          WIN / TP HIT (+2.0R)
                        </span>
                      ) : isLoss ? (
                        <span className="inline-flex items-center text-[10px] px-2 py-0.5 rounded bg-rose-950/70 border border-rose-800 text-rose-300 font-bold">
                          <XCircle className="h-2.5 w-2.5 mr-1" />
                          SL HIT (-1.0R)
                        </span>
                      ) : (
                        <span className="inline-flex items-center text-[10px] px-2 py-0.5 rounded bg-cyan-950/70 border border-cyan-800 text-cyan-300 font-bold">
                          BREAKEVEN (0.0R)
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 text-slate-500 text-[11px]">
                      {t.closed_at ? new Date(t.closed_at).toLocaleString() : '—'}
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
