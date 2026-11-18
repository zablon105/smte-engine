/**
 * api.js
 * Frontend HTTP client communicating with SMTE FastAPI REST Backend.
 */

const API_BASE = '/api/v1';

async function fetchJson(endpoint, options = {}) {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
      },
      ...options,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return await res.json();
  } catch (error) {
    console.warn(`[API ERROR] ${endpoint}:`, error.message);
    throw error;
  }
}

export const api = {
  // Health
  getHealth: async () => {
    try {
      const res = await fetch('/health');
      return await res.json();
    } catch {
      return { status: 'OFFLINE', mt5_connected: false, database_connected: false };
    }
  },

  // Account & Analytics
  getAccount: () => fetchJson('/analytics/account'),
  getPerformance: () => fetchJson('/analytics/performance'),
  getStrategies: () => fetchJson('/analytics/strategies'),

  // Trades
  getOpenTrades: () => fetchJson('/trades/open'),
  getTradeHistory: (limit = 50, offset = 0, symbol = '') => {
    const q = new URLSearchParams({ limit, offset });
    if (symbol) q.append('symbol', symbol);
    return fetchJson(`/trades/history?${q.toString()}`);
  },
  moveToBreakeven: (ticket) =>
    fetchJson('/trades/breakeven', {
      method: 'POST',
      body: JSON.stringify({ ticket }),
    }),
  closeTrade: (ticket) =>
    fetchJson('/trades/close', {
      method: 'POST',
      body: JSON.stringify({ ticket }),
    }),

  // Signals
  getActiveSignals: (limit = 20) => fetchJson(`/signals/active?limit=${limit}`),
  runLiveScan: (strategy = 'all', timeframe = 'M5') =>
    fetchJson(`/signals/scan-now?strategy=${strategy}&timeframe=${timeframe}`),

  // Market Data
  getInstruments: () => fetchJson('/market/instruments'),
  getCandles: (symbol = 'EURUSD.m', timeframe = 'M5', count = 100) =>
    fetchJson(`/market/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&count=${count}`),
  getSessionInfo: () => fetchJson('/market/sessions'),
};
