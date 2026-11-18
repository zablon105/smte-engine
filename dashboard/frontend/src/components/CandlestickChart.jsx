import React, { useState, useEffect, useMemo, useRef } from 'react';
import { BarChart3, Maximize2, RefreshCw, Crosshair } from 'lucide-react';
import { api } from '../services/api';

const SYMBOLS = ['EURUSD.m', 'GBPUSD.m', 'USDJPY.m', 'XAUUSD.m', 'BTCUSD.m'];
const TIMEFRAMES = ['M1', 'M5', 'M15', 'H1'];

export default function CandlestickChart({ openTrades }) {
  const [symbol, setSymbol] = useState('EURUSD.m');
  const [timeframe, setTimeframe] = useState('M5');
  const [candles, setCandles] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hoveredCandle, setHoveredCandle] = useState(null);
  const containerRef = useRef(null);

  const loadCandles = async () => {
    setIsLoading(true);
    try {
      const data = await api.getCandles(symbol, timeframe, 65);
      setCandles(data || []);
    } catch (e) {
      console.warn('Failed to load candles:', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCandles();
    const interval = setInterval(loadCandles, 10000); // 10s auto-refresh
    return () => clearInterval(interval);
  }, [symbol, timeframe]);

  // Find active trade on this symbol
  const activeTrade = useMemo(() => {
    return openTrades?.find((t) => t.symbol === symbol);
  }, [openTrades, symbol]);

  // Calculate scales for SVG rendering
  const chartMetrics = useMemo(() => {
    if (!candles || candles.length === 0) return null;
    let minPrice = Infinity;
    let maxPrice = -Infinity;

    candles.forEach((c) => {
      if (c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
    });

    if (activeTrade) {
      if (activeTrade.stop_loss && activeTrade.stop_loss < minPrice) minPrice = activeTrade.stop_loss;
      if (activeTrade.take_profit && activeTrade.take_profit > maxPrice) maxPrice = activeTrade.take_profit;
      if (activeTrade.entry_price < minPrice) minPrice = activeTrade.entry_price;
      if (activeTrade.entry_price > maxPrice) maxPrice = activeTrade.entry_price;
    }

    const padding = (maxPrice - minPrice) * 0.08 || 0.0005;
    return {
      min: minPrice - padding,
      max: maxPrice + padding,
      range: maxPrice - minPrice + padding * 2,
    };
  }, [candles, activeTrade]);

  const width = 850;
  const height = 360;
  const chartPaddingTop = 20;
  const chartPaddingBottom = 30;
  const chartPaddingRight = 75;
  const usableHeight = height - chartPaddingTop - chartPaddingBottom;
  const usableWidth = width - chartPaddingRight;

  const getY = (price) => {
    if (!chartMetrics || chartMetrics.range === 0) return height / 2;
    return chartPaddingTop + ((chartMetrics.max - price) / chartMetrics.range) * usableHeight;
  };

  const candleWidth = useMemo(() => {
    if (!candles || candles.length === 0) return 8;
    return Math.max(4, Math.min(14, (usableWidth / candles.length) * 0.7));
  }, [candles, usableWidth]);

  return (
    <div className="bg-[#111726] border border-[#1E293B] rounded-xl p-5 shadow-lg flex flex-col h-full">
      {/* Chart Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-[#1E293B]">
        {/* Symbol Selector */}
        <div className="flex items-center space-x-1 bg-[#0B0E14] p-1 rounded-lg border border-[#1E293B]">
          {SYMBOLS.map((s) => (
            <button
              key={s}
              onClick={() => setSymbol(s)}
              className={`px-2.5 py-1 text-xs font-mono rounded font-medium transition-all ${
                symbol === s
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-[0_0_10px_rgba(6,182,212,0.2)]'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {s.replace('.m', '')}
            </button>
          ))}
        </div>

        {/* Timeframe Selector */}
        <div className="flex items-center space-x-1 bg-[#0B0E14] p-1 rounded-lg border border-[#1E293B]">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-2.5 py-1 text-xs font-mono rounded font-medium transition-all ${
                timeframe === tf
                  ? 'bg-slate-700 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>

        {/* Live Candlestick Readout */}
        <div className="hidden md:flex items-center space-x-3 text-xs font-mono">
          {hoveredCandle ? (
            <div className="flex items-center space-x-3 text-[11px] bg-[#0B0E14] px-3 py-1 rounded border border-[#1E293B]">
              <span className="text-slate-400">O: <span className="text-slate-200 font-bold">{hoveredCandle.open}</span></span>
              <span className="text-slate-400">H: <span className="text-slate-200 font-bold">{hoveredCandle.high}</span></span>
              <span className="text-slate-400">L: <span className="text-slate-200 font-bold">{hoveredCandle.low}</span></span>
              <span className="text-slate-400">C: <span className={`font-bold ${hoveredCandle.close >= hoveredCandle.open ? 'text-emerald-400' : 'text-rose-400'}`}>{hoveredCandle.close}</span></span>
              <span className="text-slate-500">Vol: {hoveredCandle.volume}</span>
            </div>
          ) : (
            candles.length > 0 && (
              <div className="flex items-center space-x-2 text-[11px] text-slate-400">
                <span>Latest:</span>
                <span
                  className={`font-bold ${
                    candles[candles.length - 1].close >= candles[candles.length - 1].open
                      ? 'text-emerald-400'
                      : 'text-rose-400'
                  }`}
                >
                  {candles[candles.length - 1].close}
                </span>
              </div>
            )
          )}
        </div>
      </div>

      {/* SVG Canvas Area */}
      <div
        ref={containerRef}
        className="relative flex-1 min-h-[360px] w-full pt-3 flex items-center justify-center overflow-hidden"
      >
        {isLoading && candles.length === 0 ? (
          <div className="flex items-center space-x-2 text-slate-400 font-mono text-sm">
            <RefreshCw className="h-4 w-4 animate-spin text-cyan-400" />
            <span>Streaming institutional candles...</span>
          </div>
        ) : candles.length === 0 ? (
          <div className="text-slate-500 font-mono text-sm">No candle data available</div>
        ) : (
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-full select-none cursor-crosshair"
            preserveAspectRatio="none"
          >
            {/* Horizontal Grid Lines & Price Labels */}
            {[0, 0.25, 0.5, 0.75, 1.0].map((ratio) => {
              const price = chartMetrics.max - ratio * chartMetrics.range;
              const y = chartPaddingTop + ratio * usableHeight;
              return (
                <g key={ratio}>
                  <line
                    x1={0}
                    y1={y}
                    x2={usableWidth}
                    y2={y}
                    stroke="#1E293B"
                    strokeDasharray="3 3"
                    strokeWidth="0.8"
                  />
                  <text
                    x={usableWidth + 8}
                    y={y + 3.5}
                    fill="#64748B"
                    fontSize="10"
                    fontFamily="monospace"
                  >
                    {price.toFixed(symbol.includes('JPY') || symbol.includes('XAU') || symbol.includes('BTC') ? 2 : 5)}
                  </text>
                </g>
              );
            })}

            {/* Active Position Overlay Lines (Entry, SL, TP) */}
            {activeTrade && (
              <g className="animate-fade-in">
                {/* Take Profit Target Line */}
                {activeTrade.take_profit && (
                  <g>
                    <line
                      x1={0}
                      y1={getY(activeTrade.take_profit)}
                      x2={usableWidth}
                      y2={getY(activeTrade.take_profit)}
                      stroke="#10B981"
                      strokeWidth="1.5"
                      strokeDasharray="4 2"
                    />
                    <rect
                      x={usableWidth - 55}
                      y={getY(activeTrade.take_profit) - 10}
                      width="50"
                      height="16"
                      rx="3"
                      fill="#064E3B"
                    />
                    <text
                      x={usableWidth - 30}
                      y={getY(activeTrade.take_profit) + 2}
                      textAnchor="middle"
                      fill="#34D399"
                      fontSize="9"
                      fontFamily="monospace"
                      fontWeight="bold"
                    >
                      TP: {activeTrade.take_profit}
                    </text>
                  </g>
                )}

                {/* Stop Loss Line */}
                {activeTrade.stop_loss && (
                  <g>
                    <line
                      x1={0}
                      y1={getY(activeTrade.stop_loss)}
                      x2={usableWidth}
                      y2={getY(activeTrade.stop_loss)}
                      stroke="#F43F5E"
                      strokeWidth="1.5"
                      strokeDasharray="4 2"
                    />
                    <rect
                      x={usableWidth - 55}
                      y={getY(activeTrade.stop_loss) - 10}
                      width="50"
                      height="16"
                      rx="3"
                      fill="#881337"
                    />
                    <text
                      x={usableWidth - 30}
                      y={getY(activeTrade.stop_loss) + 2}
                      textAnchor="middle"
                      fill="#FDA4AF"
                      fontSize="9"
                      fontFamily="monospace"
                      fontWeight="bold"
                    >
                      SL: {activeTrade.stop_loss}
                    </text>
                  </g>
                )}

                {/* Entry Price Line */}
                <g>
                  <line
                    x1={0}
                    y1={getY(activeTrade.entry_price)}
                    x2={usableWidth}
                    y2={getY(activeTrade.entry_price)}
                    stroke="#06B6D4"
                    strokeWidth="1.5"
                  />
                  <rect
                    x={usableWidth - 65}
                    y={getY(activeTrade.entry_price) - 10}
                    width="60"
                    height="16"
                    rx="3"
                    fill="#164E63"
                  />
                  <text
                    x={usableWidth - 35}
                    y={getY(activeTrade.entry_price) + 2}
                    textAnchor="middle"
                    fill="#67E8F9"
                    fontSize="9"
                    fontFamily="monospace"
                    fontWeight="bold"
                  >
                    ENTRY: {activeTrade.entry_price}
                  </text>
                </g>
              </g>
            )}

            {/* Candlesticks */}
            {candles.map((c, i) => {
              const x = (i / (candles.length - 1 || 1)) * (usableWidth - candleWidth * 2) + candleWidth;
              const isBull = c.close >= c.open;
              const color = isBull ? '#10B981' : '#F43F5E';
              const yHigh = getY(c.high);
              const yLow = getY(c.low);
              const yOpen = getY(c.open);
              const yClose = getY(c.close);
              const bodyTop = Math.min(yOpen, yClose);
              const bodyHeight = Math.max(2, Math.abs(yClose - yOpen));

              return (
                <g
                  key={c.time}
                  onMouseEnter={() => setHoveredCandle(c)}
                  onMouseLeave={() => setHoveredCandle(null)}
                  className="transition-opacity hover:opacity-80"
                >
                  {/* Wick */}
                  <line
                    x1={x}
                    y1={yHigh}
                    x2={x}
                    y2={yLow}
                    stroke={color}
                    strokeWidth="1.2"
                  />
                  {/* Body */}
                  <rect
                    x={x - candleWidth / 2}
                    y={bodyTop}
                    width={candleWidth}
                    height={bodyHeight}
                    fill={color}
                    rx="1"
                  />
                </g>
              );
            })}
          </svg>
        )}
      </div>

      {/* Chart Footer with Active DOL & Execution details */}
      <div className="pt-3 border-t border-[#1E293B] flex items-center justify-between text-xs font-mono text-slate-400">
        <div className="flex items-center space-x-2">
          <span className="h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.8)]" />
          <span>Institutional Stream: <span className="text-slate-200 font-medium">{symbol}</span> ({timeframe})</span>
        </div>
        {activeTrade ? (
          <div className="text-cyan-400 font-semibold">
            Active Position: #{activeTrade.mt5_ticket} ({activeTrade.direction} {activeTrade.lot_size} lots)
          </div>
        ) : (
          <div className="text-slate-500">No active position on {symbol}</div>
        )}
      </div>
    </div>
  );
}
