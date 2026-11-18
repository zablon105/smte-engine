import React, { useState, useEffect, useCallback } from 'react';
import Header from './components/Header';
import CandlestickChart from './components/CandlestickChart';
import ActivePositions from './components/ActivePositions';
import SignalFeed from './components/SignalFeed';
import PerformanceMatrix from './components/PerformanceMatrix';
import EquityCurve from './components/EquityCurve';
import TradeJournal from './components/TradeJournal';
import { api } from './services/api';
import { Terminal, Shield, AlertTriangle } from 'lucide-react';

export default function App() {
  const [account, setAccount] = useState(null);
  const [session, setSession] = useState(null);
  const [openTrades, setOpenTrades] = useState([]);
  const [signals, setSignals] = useState([]);
  const [tradeHistory, setTradeHistory] = useState([]);
  const [performance, setPerformance] = useState(null);
  const [strategies, setStrategies] = useState([]);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const loadAllData = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const [acc, sess, trades, sigs, hist, perf, strats] = await Promise.allSettled([
        api.getAccount(),
        api.getSessionInfo(),
        api.getOpenTrades(),
        api.getActiveSignals(15),
        api.getTradeHistory(30),
        api.getPerformance(),
        api.getStrategies(),
      ]);

      if (acc.status === 'fulfilled') setAccount(acc.value);
      if (sess.status === 'fulfilled') setSession(sess.value);
      if (trades.status === 'fulfilled') setOpenTrades(trades.value);
      if (sigs.status === 'fulfilled') setSignals(sigs.value);
      if (hist.status === 'fulfilled') setTradeHistory(hist.value);
      if (perf.status === 'fulfilled') setPerformance(perf.value);
      if (strats.status === 'fulfilled') setStrategies(strats.value);
    } catch (err) {
      console.warn('Dashboard data fetch error:', err);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadAllData();
    const interval = setInterval(loadAllData, 6000); // 6s institutional poll
    return () => clearInterval(interval);
  }, [loadAllData]);

  return (
    <div className="min-h-screen bg-[#0B0E14] text-slate-100 flex flex-col font-sans">
      {/* Top Institutional Header */}
      <Header
        account={account}
        session={session}
        onRefresh={loadAllData}
        isRefreshing={isRefreshing}
      />

      {/* Main Trading Floor Grid */}
      <main className="flex-1 p-6 space-y-6 max-w-[1700px] w-full mx-auto">
        {/* Real-Time Operational Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 rounded-lg bg-[#0E1422] border border-[#1E293B] text-xs font-mono">
          <div className="flex items-center space-x-2 text-cyan-400">
            <Terminal className="h-4 w-4" />
            <span className="font-bold">SYSTEM STATUS:</span>
            <span className="text-slate-300">
              Autonomous Scalper Daemon is active &bull; Monitoring 5 pairs on M5 every 15s &bull; Safe 0.01 micro-lots
            </span>
          </div>

          <div className="flex items-center space-x-4 text-[11px] text-slate-400">
            <span>
              Target R:R: <strong className="text-emerald-400">2.0R</strong>
            </span>
            <span>
              Breakeven Trigger: <strong className="text-cyan-300">+1.0R</strong>
            </span>
            <span>
              Risk Engine: <strong className="text-amber-300">1 Position / Symbol</strong>
            </span>
          </div>
        </div>

        {/* Top Grid: Interactive Chart + Active Positions + Signal Scanner */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Center Column: Chart & Active Positions */}
          <div className="lg:col-span-8 space-y-6">
            <div className="h-[460px]">
              <CandlestickChart openTrades={openTrades} />
            </div>

            <div>
              <ActivePositions positions={openTrades} onUpdate={loadAllData} />
            </div>
          </div>

          {/* Right Column: Signal Scanner Feed */}
          <div className="lg:col-span-4 h-full">
            <SignalFeed signals={signals} />
          </div>
        </div>

        {/* Middle Grid: Strategy Benchmarks & Live Equity Curve */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-7">
            <EquityCurve performance={performance} />
          </div>
          <div className="lg:col-span-5">
            <PerformanceMatrix strategies={strategies} />
          </div>
        </div>

        {/* Bottom Section: Closed Trades Journal */}
        <div>
          <TradeJournal trades={tradeHistory} onRefresh={loadAllData} />
        </div>
      </main>

      {/* Institutional Footer */}
      <footer className="border-t border-[#1E293B] bg-[#0A0D14] px-6 py-4 text-center text-xs font-mono text-slate-500">
        SMTE (Smart Money Trading Engine) &bull; Institutional Quantitative Algorithmic Architecture &bull; MetaTrader 5 + PostgreSQL 16
      </footer>
    </div>
  );
}
