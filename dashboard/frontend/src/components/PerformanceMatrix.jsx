import React from 'react';
import { Award, TrendingUp, BarChart2, CheckCircle } from 'lucide-react';

export default function PerformanceMatrix({ strategies }) {
  if (!strategies || strategies.length === 0) return null;

  return (
    <div className="bg-[#111726] border border-[#1E293B] rounded-xl p-5 shadow-lg">
      <div className="flex items-center space-x-2 pb-4 border-b border-[#1E293B]">
        <Award className="h-5 w-5 text-cyan-400" />
        <h2 className="font-mono font-bold text-sm tracking-wide text-white uppercase">
          Institutional Model Benchmarks (Historical Backtests)
        </h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 pt-4">
        {strategies.map((s, idx) => (
          <div
            key={idx}
            className="p-4 rounded-xl bg-[#0B0E14] border border-[#1E293B] hover:border-cyan-500/30 transition-all font-mono"
          >
            <div className="flex items-center justify-between pb-2 border-b border-[#1A2338]">
              <span className="font-bold text-slate-200 text-xs truncate max-w-[170px]" title={s.strategy_name}>
                {s.strategy_name}
              </span>
              <span className="text-[10px] text-slate-500">{s.total_trades} trades</span>
            </div>

            <div className="grid grid-cols-3 gap-2 pt-3 text-center">
              <div>
                <span className="text-[10px] uppercase text-slate-500 block">Win Rate</span>
                <span className="text-emerald-400 font-bold text-sm">{s.win_rate_pct}%</span>
              </div>
              <div>
                <span className="text-[10px] uppercase text-slate-500 block">Profit Factor</span>
                <span className="text-cyan-300 font-bold text-sm">{s.profit_factor}</span>
              </div>
              <div>
                <span className="text-[10px] uppercase text-slate-500 block">Expectancy</span>
                <span className="text-amber-400 font-bold text-sm">+{s.avg_r}R</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
