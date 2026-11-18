import React from 'react';
import {
  Activity,
  ShieldCheck,
  Zap,
  Clock,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Layers,
  RefreshCw,
} from 'lucide-react';

export default function Header({ account, session, onRefresh, isRefreshing }) {
  const isProfit = (account?.floating_profit ?? 0) >= 0;

  return (
    <header className="border-b border-[#1E293B] bg-[#0E131F]/90 backdrop-blur-md px-6 py-4 sticky top-0 z-50">
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
        {/* Brand & Engine Status */}
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <div className="h-9 w-9 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 font-bold shadow-[0_0_15px_rgba(6,182,212,0.25)]">
              <Zap className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-mono font-bold tracking-wider text-base text-white">SMTE</span>
                <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-cyan-950/80 text-cyan-400 border border-cyan-800/40">
                  INSTITUTIONAL DESK v2.0
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-mono">
                Smart Money Concepts &bull; CRT &bull; Unicorn &bull; Turtle Soup
              </p>
            </div>
          </div>

          <div className="h-8 w-px bg-[#1E293B] hidden md:block" />

          {/* Connection Status Pill */}
          <div className="hidden sm:flex items-center space-x-2 text-xs font-mono px-3 py-1.5 rounded-md bg-[#141A29] border border-[#1E293B]">
            <span
              className={`h-2 w-2 rounded-full ${
                account?.is_connected
                  ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)] animate-pulse'
                  : 'bg-rose-500'
              }`}
            />
            <span className="text-slate-300">
              {account?.is_connected ? (
                <>
                  MT5 <span className="text-emerald-400 font-semibold">{account?.server}</span> (#{account?.login})
                </>
              ) : (
                <span className="text-rose-400">MT5 Disconnected</span>
              )}
            </span>
          </div>

          {/* Killzone Pill */}
          {session && (
            <div className="hidden xl:flex items-center space-x-2 text-xs font-mono px-3 py-1.5 rounded-md bg-[#16172E] border border-indigo-900/40">
              <Clock className="h-3.5 w-3.5 text-indigo-400" />
              <span className="text-indigo-200">
                {session.is_killzone ? (
                  <span className="text-amber-300 font-bold flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-ping" />
                    {session.current_killzone}
                  </span>
                ) : (
                  <span>{session.active_session}</span>
                )}
              </span>
            </div>
          )}
        </div>

        {/* Global Account Metrics Strip */}
        <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto justify-between lg:justify-end">
          {/* Balance */}
          <div className="bg-[#111726] border border-[#1E293B] rounded-lg px-3.5 py-2 min-w-[120px]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block tracking-wider">Balance</span>
            <span className="font-mono text-sm font-semibold text-slate-100">
              ${account?.balance?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '0.00'}
            </span>
          </div>

          {/* Equity */}
          <div className="bg-[#111726] border border-[#1E293B] rounded-lg px-3.5 py-2 min-w-[120px]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block tracking-wider">Net Equity</span>
            <span className="font-mono text-sm font-semibold text-cyan-300">
              ${account?.equity?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) ?? '0.00'}
            </span>
          </div>

          {/* Floating P&L */}
          <div
            className={`border rounded-lg px-3.5 py-2 min-w-[120px] ${
              isProfit
                ? 'bg-emerald-950/20 border-emerald-900/40 text-emerald-400'
                : 'bg-rose-950/20 border-rose-900/40 text-rose-400'
            }`}
          >
            <span className="text-[10px] uppercase font-mono block tracking-wider opacity-80 flex items-center justify-between">
              Floating P&L
              {isProfit ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
            </span>
            <span className="font-mono text-sm font-bold">
              {isProfit ? '+' : ''}${account?.floating_profit?.toFixed(2) ?? '0.00'}
            </span>
          </div>

          {/* Open Positions Counter */}
          <div className="bg-[#111726] border border-[#1E293B] rounded-lg px-3.5 py-2 text-center min-w-[90px]">
            <span className="text-[10px] uppercase font-mono text-slate-400 block tracking-wider">Active Pos</span>
            <span className="font-mono text-sm font-bold text-amber-400">
              {account?.open_positions_count ?? 0}
            </span>
          </div>

          {/* Manual Refresh Button */}
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="p-2.5 rounded-lg bg-[#141A29] border border-[#1E293B] text-slate-300 hover:text-cyan-400 hover:border-cyan-500/40 transition-colors"
            title="Refresh All Terminal Feeds"
          >
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin text-cyan-400' : ''}`} />
          </button>
        </div>
      </div>
    </header>
  );
}
