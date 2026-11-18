import React, { useState } from 'react';
import { Target, Search, ArrowUpRight, ArrowDownRight, Layers, CheckCircle2 } from 'lucide-react';
import { api } from '../services/api';

const STRATEGIES = [
  { id: 'all', label: 'ALL STRATEGIES' },
  { id: 'turtle_soup', label: 'TURTLE SOUP' },
  { id: 'unicorn', label: 'UNICORN' },
  { id: 'crt', label: 'CRT' },
  { id: 'po3', label: 'PO3 / JUDAS' },
];

export default function SignalFeed({ signals }) {
  const [strategy, setStrategy] = useState('all');
  const [timeframe, setTimeframe] = useState('M5');
  const [isScanning, setIsScanning] = useState(false);
  const [liveScanResult, setLiveScanResult] = useState(null);

  const handleScanNow = async () => {
    setIsScanning(true);
    setLiveScanResult(null);
    try {
      const data = await api.runLiveScan(strategy, timeframe);
      setLiveScanResult(data);
    } catch (err) {
      console.warn('Scan failed:', err);
    } finally {
      setIsScanning(false);
    }
  };

  return (
    <div className="bg-[#111726] border border-[#1E293B] rounded-xl p-5 shadow-lg flex flex-col h-full">
      <div className="flex items-center justify-between pb-4 border-b border-[#1E293B]">
        <div className="flex items-center space-x-2">
          <Target className="h-5 w-5 text-amber-400" />
          <h2 className="font-mono font-bold text-sm tracking-wide text-white uppercase">
            Institutional Signal Scanner
          </h2>
        </div>

        <button
          onClick={handleScanNow}
          disabled={isScanning}
          className="px-3 py-1.5 text-xs font-mono rounded bg-amber-500/10 border border-amber-500/30 text-amber-300 hover:bg-amber-500/20 transition-all flex items-center space-x-1.5 shadow-[0_0_10px_rgba(245,158,11,0.15)] disabled:opacity-50"
        >
          <Search className={`h-3.5 w-3.5 ${isScanning ? 'animate-spin' : ''}`} />
          <span>{isScanning ? 'Scanning...' : 'Scan Now'}</span>
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex flex-wrap gap-1.5 py-3 border-b border-[#1E293B]">
        {STRATEGIES.map((s) => (
          <button
            key={s.id}
            onClick={() => setStrategy(s.id)}
            className={`px-2.5 py-1 text-[11px] font-mono rounded transition-all ${
              strategy === s.id
                ? 'bg-cyan-950 text-cyan-300 border border-cyan-800 font-semibold'
                : 'text-slate-400 hover:text-slate-200 bg-[#0B0E14]'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* On-Demand Scan Result Banner */}
      {liveScanResult && (
        <div className="mt-3 p-3 rounded-lg bg-[#0B0E14] border border-cyan-900/40 text-xs font-mono">
          <div className="flex items-center justify-between text-cyan-300 font-bold mb-1">
            <span>On-Demand Scan Complete</span>
            <span>{liveScanResult.count} Setups Detected</span>
          </div>
          {liveScanResult.count === 0 ? (
            <p className="text-slate-400 text-[11px]">
              No {strategy.toUpperCase()} setups currently qualify on {timeframe}. Institutional conditions require strict sweep + displacement alignment.
            </p>
          ) : (
            <div className="space-y-2 mt-2">
              {liveScanResult.setups.map((s, idx) => (
                <div key={idx} className="p-2 rounded bg-[#111726] border border-[#1E293B] flex items-center justify-between">
                  <div>
                    <span className="font-bold text-slate-100">{s.symbol}</span>
                    <span className="ml-2 text-cyan-400 text-[10px] uppercase">{s.strategy}</span>
                  </div>
                  <div className="text-right">
                    <span className={s.direction === 'BUY' ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                      {s.direction} @ {s.entry_price}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Signals Feed List */}
      <div className="space-y-3 mt-4 flex-1 overflow-y-auto max-h-[380px] pr-1">
        {(!signals || signals.length === 0) ? (
          <div className="text-center py-8 text-slate-500 font-mono text-xs">
            <Layers className="h-6 w-6 mx-auto mb-2 opacity-50" />
            <p>No historical signals recorded in current session.</p>
          </div>
        ) : (
          signals.map((sig) => {
            const isBuy = sig.signal_direction === 'BUY';
            return (
              <div
                key={sig.id}
                className="p-3.5 rounded-lg bg-[#0E1422] border border-[#1E293B] hover:border-cyan-900/60 transition-colors font-mono text-xs"
              >
                <div className="flex items-center justify-between pb-2 border-b border-[#1A2338]">
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-slate-100 text-sm">{sig.symbol}</span>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center space-x-0.5 ${
                        isBuy
                          ? 'bg-emerald-950/70 text-emerald-400 border border-emerald-800/40'
                          : 'bg-rose-950/70 text-rose-400 border border-rose-800/40'
                      }`}
                    >
                      {isBuy ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                      <span>{sig.signal_direction}</span>
                    </span>
                  </div>

                  <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800/50">
                    Score: {sig.total_score}/25
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 pt-2.5 text-[11px]">
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">Entry</span>
                    <span className="text-slate-200 font-semibold">{sig.entry_price}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">Stop Loss</span>
                    <span className="text-rose-400 font-semibold">{sig.stop_loss}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase">Target (2.0R)</span>
                    <span className="text-emerald-400 font-semibold">{sig.take_profit}</span>
                  </div>
                </div>

                {sig.details && (
                  <div className="mt-2 text-[10px] text-slate-400 bg-[#0B0E14] px-2.5 py-1 rounded border border-[#1A2338]">
                    {sig.details}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
