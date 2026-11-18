import React, { useMemo } from 'react';
import { TrendingUp, DollarSign, Activity } from 'lucide-react';

export default function EquityCurve({ performance }) {
  const curve = performance?.equity_curve || [];

  const { points, areaPoints, minVal, maxVal } = useMemo(() => {
    if (!curve || curve.length === 0) return { points: '', areaPoints: '', minVal: 0, maxVal: 0 };

    let min = 0;
    let max = 0;
    curve.forEach((c) => {
      if (c.cumulative_pnl < min) min = c.cumulative_pnl;
      if (c.cumulative_pnl > max) max = c.cumulative_pnl;
    });

    const pad = (max - min) * 0.15 || 5;
    const chartMin = min - pad;
    const chartMax = max + pad;
    const range = chartMax - chartMin || 1;

    const w = 700;
    const h = 200;
    const ptList = curve.map((c, idx) => {
      const x = (idx / (curve.length - 1 || 1)) * w;
      const y = h - ((c.cumulative_pnl - chartMin) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });

    const pts = ptList.join(' ');
    const zeroY = h - ((0 - chartMin) / range) * h;
    const area = `0,${zeroY.toFixed(1)} ${pts} ${w},${zeroY.toFixed(1)}`;

    return { points: pts, areaPoints: area, minVal: min, maxVal: max };
  }, [curve]);

  return (
    <div className="bg-[#111726] border border-[#1E293B] rounded-xl p-5 shadow-lg">
      <div className="flex items-center justify-between pb-4 border-b border-[#1E293B]">
        <div className="flex items-center space-x-2">
          <TrendingUp className="h-5 w-5 text-emerald-400" />
          <h2 className="font-mono font-bold text-sm tracking-wide text-white uppercase">
            Live Equity Curve & Net Realized P&L
          </h2>
        </div>

        <div className="flex items-center space-x-4 text-xs font-mono">
          <div>
            <span className="text-slate-400">Total Closed:</span>{' '}
            <span className="text-white font-bold">{performance?.total_trades ?? 0}</span>
          </div>
          <div>
            <span className="text-slate-400">Net Realized:</span>{' '}
            <span className={`font-bold ${(performance?.net_profit ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {(performance?.net_profit ?? 0) >= 0 ? '+' : ''}${performance?.net_profit?.toFixed(2) ?? '0.00'}
            </span>
          </div>
        </div>
      </div>

      <div className="pt-4 h-[220px] w-full flex items-center justify-center">
        {curve.length < 2 ? (
          <div className="text-slate-500 font-mono text-xs text-center py-10">
            <Activity className="h-6 w-6 mx-auto mb-2 opacity-40" />
            <p>Accumulating closed trade data for equity curve visualization.</p>
          </div>
        ) : (
          <svg viewBox="0 0 700 200" className="w-full h-full select-none" preserveAspectRatio="none">
            <defs>
              <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10B981" stopOpacity="0.3" />
                <stop offset="100%" stopColor="#10B981" stopOpacity="0.0" />
              </linearGradient>
            </defs>

            {/* Zero Line */}
            <line x1="0" y1="100" x2="700" y2="100" stroke="#1E293B" strokeDasharray="3 3" />

            {/* Gradient Area */}
            <polygon points={areaPoints} fill="url(#equityGradient)" />

            {/* Main Equity Path */}
            <polyline fill="none" stroke="#10B981" strokeWidth="2.5" points={points} />

            {/* Trade dots */}
            {curve.map((c, i) => {
              const x = (i / (curve.length - 1)) * 700;
              const range = (maxVal - minVal + 10) || 1;
              const y = 200 - ((c.cumulative_pnl - (minVal - 5)) / range) * 200;
              return (
                <circle
                  key={i}
                  cx={x}
                  cy={y}
                  r="3.5"
                  fill="#0B0E14"
                  stroke={c.profit >= 0 ? '#10B981' : '#F43F5E'}
                  strokeWidth="2"
                />
              );
            })}
          </svg>
        )}
      </div>
    </div>
  );
}
