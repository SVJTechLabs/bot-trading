import { useState, useEffect, useRef, useCallback } from "react";

// ─────────────────────────────────────────────────────────────
//  🌐 LIVE GCP SERVER — Your bot running 24/7
// ─────────────────────────────────────────────────────────────
const GCP_IP = "34.24.44.51";
const API_BASE = `/api`; // Proxy via vercel.json to avoid Mixed Content block
const WS_URL = `ws://${GCP_IP}:8000/ws`; // Note: Browsers block WS over HTTPS, will fail safely

// ─────────────────────────────────────────────────────────────
//  🔑 goldapi.io key for real spot price
// ─────────────────────────────────────────────────────────────
const GOLD_API_KEY = "88c58e6caf99e26e6d436caf96865a1980a899919dc21ffe965bf8b148d5c8dc";

const C = {
    bg: "#080810", panel: "#0E0E18", border: "#1A1A2E",
    gold: "#F5C518", muted: "#525270", text: "#EAEAF8",
    green: "#00E676", red: "#FF4560", blue: "#4FC3F7",
};

// ─────────────────────────────────────────────────────────────
//  REAL PRICE HOOK (goldapi → Yahoo → simulate)
// ─────────────────────────────────────────────────────────────
function useRealPrice() {
    const [price, setPrice] = useState(null);
    const [prev, setPrev] = useState(null);
    const [open, setOpen] = useState(null);
    const [high, setHigh] = useState(null);
    const [low, setLow] = useState(null);
    const [history, setHistory] = useState([]);
    const [source, setSource] = useState("connecting…");
    const [lastUp, setLastUp] = useState(null);

    const updatePrice = useCallback((p) => {
        setPrice(cur => { setPrev(cur ?? p); return p; });
        setHistory(h => [...h.slice(-99), p]);
        setLastUp(new Date().toLocaleTimeString());
    }, []);

    const tryGoldAPI = useCallback(async () => {
        if (!GOLD_API_KEY) return false;
        const TARGET = "https://www.goldapi.io/api/XAU/USD";
        const PROXIES = [
            `https://corsproxy.io/?${encodeURIComponent(TARGET)}`,
            `https://api.allorigins.win/get?url=${encodeURIComponent(TARGET)}`,
        ];
        for (const proxyUrl of PROXIES) {
            try {
                const r = await fetch(proxyUrl, { headers: { "x-access-token": GOLD_API_KEY } });
                if (!r.ok) continue;
                const raw = await r.json();
                const d = raw.contents ? JSON.parse(raw.contents) : raw;
                if (!d?.price) continue;
                updatePrice(parseFloat(d.price.toFixed(2)));
                setOpen(d.open_price ? parseFloat(d.open_price.toFixed(2)) : null);
                setHigh(d.high_price ? parseFloat(d.high_price.toFixed(2)) : null);
                setLow(d.low_price ? parseFloat(d.low_price.toFixed(2)) : null);
                setSource("goldapi.io ✓ LIVE");
                return true;
            } catch { continue; }
        }
        return false;
    }, [updatePrice]);

    const tryYahoo = useCallback(async () => {
        for (const url of [
            "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d",
            "https://query2.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d",
        ]) {
            try {
                const r = await fetch(url);
                if (!r.ok) continue;
                const d = await r.json();
                const meta = d?.chart?.result?.[0]?.meta;
                const p = meta?.regularMarketPrice;
                if (!p) continue;
                updatePrice(parseFloat(p.toFixed(2)));
                setHigh(meta.regularMarketDayHigh ? parseFloat(meta.regularMarketDayHigh.toFixed(2)) : null);
                setLow(meta.regularMarketDayLow ? parseFloat(meta.regularMarketDayLow.toFixed(2)) : null);
                setOpen(meta.chartPreviousClose ? parseFloat(meta.chartPreviousClose.toFixed(2)) : null);
                setSource("Yahoo Finance ✓ LIVE");
                return true;
            } catch { continue; }
        }
        return false;
    }, [updatePrice]);

    const tryBackend = useCallback(async () => {
        try {
            const r = await fetch(`${API_BASE}/market/price`);
            if (!r.ok) return false;
            const d = await r.json();
            if (!d?.price) return false;
            updatePrice(parseFloat(d.price.toFixed(2)));
            setSource("GCP Server ✓ LIVE");
            return true;
        } catch { return false; }
    }, [updatePrice]);

    const startSim = useCallback(() => {
        setSource("simulated ~$3300 (open dashboard on your server for live)");
        let p = 3300.0;
        updatePrice(p);
        setOpen(3280.0); setHigh(3320.0); setLow(3275.0);
        return setInterval(() => {
            p = parseFloat((p + (Math.random() - 0.492) * 0.85).toFixed(2));
            updatePrice(p);
        }, 1200);
    }, [updatePrice]);

    useEffect(() => {
        let simTimer = null, pollTimer = null;
        const init = async () => {
            if (await tryBackend()) { pollTimer = setInterval(tryBackend, 3000); return; }
            if (await tryGoldAPI()) { pollTimer = setInterval(tryGoldAPI, 10000); return; }
            if (await tryYahoo()) { pollTimer = setInterval(tryYahoo, 15000); return; }
            simTimer = startSim();
        };
        init();
        return () => { clearInterval(simTimer); clearInterval(pollTimer); };
    }, [tryBackend, tryGoldAPI, tryYahoo, startSim]);

    const delta = price && prev ? parseFloat((price - prev).toFixed(2)) : 0;
    const dayChg = price && open ? parseFloat((price - open).toFixed(2)) : null;
    const dayPct = dayChg && open ? parseFloat(((dayChg / open) * 100).toFixed(2)) : null;
    return { price, delta, open, high, low, history, source, lastUp, dayChg, dayPct };
}

// ─────────────────────────────────────────────────────────────
//  GCP BOT API HOOK — polls /bot/status, /trades, /signals
// ─────────────────────────────────────────────────────────────
function useBotAPI() {
    const [botStatus, setBotStatus] = useState(null);   // /bot/status
    const [trades, setTrades] = useState([]);      // /trades
    const [signal, setSignal] = useState(null);    // /market/analysis
    const [marketConds, setMarketConds] = useState(null); // /market/signals
    const [apiOnline, setApiOnline] = useState(null);    // null=checking, true, false
    const [lastSync, setLastSync] = useState(null);
    const wsRef = useRef(null);

    const poll = useCallback(async () => {
        try {
            const [hRes, tRes, sigRes, condRes, acRes] = await Promise.all([
                fetch(`${API_BASE}/bot/status`, { signal: AbortSignal.timeout(10000) }),
                fetch(`${API_BASE}/trades`, { signal: AbortSignal.timeout(10000) }),
                fetch(`${API_BASE}/market/analysis`, { signal: AbortSignal.timeout(10000) }).catch(() => null),
                fetch(`${API_BASE}/market/signals`, { signal: AbortSignal.timeout(10000) }).catch(() => null),
                fetch(`${API_BASE}/account`, { signal: AbortSignal.timeout(10000) }).catch(() => null),
            ]);
            if (hRes.ok) {
                setBotStatus(await hRes.json());
                setApiOnline(true);
                setLastSync(new Date().toLocaleTimeString());
            }
            if (tRes.ok) setTrades((await tRes.json()).trades ?? []);
            if (sigRes?.ok) { const sg = await sigRes.json(); setSignal(sg); }
            if (condRes?.ok) { const cd = await condRes.json(); setMarketConds(cd.signals || null); }
            if (acRes?.ok) { const ac = await acRes.json(); setBotStatus(p => p ? { ...p, ...ac } : ac); }
        } catch {
            setApiOnline(false);
        }
    }, []);

    // WebSocket for live log lines
    const [wsLog, setWsLog] = useState([]);
    useEffect(() => {
        const connect = () => {
            try {
                const ws = new WebSocket(WS_URL);
                ws.onmessage = (e) => {
                    try {
                        const d = JSON.parse(e.data);
                        if (d.log) setWsLog(p => [...p.slice(-40), d.log]);
                    } catch { }
                };
                ws.onclose = () => setTimeout(connect, 5000);
                wsRef.current = ws;
            } catch { }
        };
        connect();
        return () => wsRef.current?.close();
    }, []);

    useEffect(() => {
        poll();
        const t = setInterval(poll, 8000);
        return () => clearInterval(t);
    }, [poll]);

    return { botStatus, trades, signal, apiOnline, lastSync, wsLog };
}

// ─────────────────────────────────────────────────────────────
//  UI COMPONENTS
// ─────────────────────────────────────────────────────────────
function Spark({ data, color, w = 220, h = 52 }) {
    if (!data?.length) return null;
    const min = Math.min(...data), max = Math.max(...data);
    const r = max - min || 1;
    const pts = data.map((v, i) =>
        `${(i / (data.length - 1)) * w},${h - ((v - min) / r) * (h - 4) - 2}`
    ).join(" ");
    const lx = w, ly = h - ((data[data.length - 1] - min) / r) * (h - 4) - 2;
    return (
        <svg width={w} height={h} style={{ display: "block", overflow: "visible" }}>
            <defs>
                <linearGradient id="sGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity=".3" />
                    <stop offset="100%" stopColor={color} stopOpacity="0" />
                </linearGradient>
            </defs>
            <polyline fill="none" stroke={color} strokeWidth="2" points={pts}
                strokeLinejoin="round" strokeLinecap="round" />
            <circle cx={lx} cy={ly} r="4" fill={color} />
            <circle cx={lx} cy={ly} r="8" fill={color} opacity=".15" />
        </svg>
    );
}

function Ring({ pct = 0, size = 68 }) {
    const r = size / 2 - 6, circ = 2 * Math.PI * r;
    const fill = circ * (1 - pct / 100);
    const col = pct >= 70 ? C.green : pct >= 55 ? C.gold : C.red;
    return (
        <svg width={size} height={size}>
            <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={C.border} strokeWidth="5" />
            <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={col} strokeWidth="5"
                strokeDasharray={circ} strokeDashoffset={fill} strokeLinecap="round"
                transform={`rotate(-90 ${size / 2} ${size / 2})`}
                style={{ transition: "stroke-dashoffset .7s ease" }} />
            <text x={size / 2} y={size / 2 + 5} textAnchor="middle"
                style={{ fill: col, fontSize: 13, fontWeight: 700, fontFamily: "'DM Mono',monospace" }}>
                {pct}%
            </text>
        </svg>
    );
}

function StatusDot({ online }) {
    const color = online === null ? C.gold : online ? C.green : C.red;
    const label = online === null ? "CHECKING" : online ? "ONLINE" : "OFFLINE";
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <div style={{
                width: 7, height: 7, borderRadius: "50%", background: color,
                boxShadow: `0 0 6px ${color}`,
                animation: online ? "blink 2s infinite" : "none",
            }} />
            <span style={{ fontSize: 9, color, letterSpacing: 1, fontFamily: "'DM Mono'" }}>{label}</span>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
//  MAIN DASHBOARD
// ─────────────────────────────────────────────────────────────
export default function Dashboard() {
    const { price, delta, open, high, low, history, source, lastUp, dayChg, dayPct } = useRealPrice();
    const { botStatus, trades, signal, marketConds, apiOnline, lastSync, wsLog } = useBotAPI();

    const [localLog, setLocalLog] = useState([
        "🟡 Dashboard initializing…",
        `🌐 Connecting to GCP server ${GCP_IP}:8000…`,
        "📡 Fetching live XAUUSD price…",
        "🛡️ Risk manager loaded",
        "✅ All systems ready",
    ]);
    const logRef = useRef(null);

    // Merge WebSocket log lines into localLog
    useEffect(() => {
        if (wsLog.length) setLocalLog(p => [...p.slice(-25), ...wsLog.slice(-3)]);
    }, [wsLog]);

    // Push API status updates
    useEffect(() => {
        if (apiOnline === true) setLocalLog(p => [...p.slice(-30), `✅ GCP API online — bot ${botStatus?.bot_running ? "RUNNING" : "STANDBY"}`]);
        if (apiOnline === false) setLocalLog(p => [...p.slice(-30), `🔴 GCP API unreachable — check server`]);
    }, [apiOnline, botStatus?.bot_running]);

    useEffect(() => {
        if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    }, [localLog]);

    // Derive display values
    const isUp = delta >= 0;
    const isUp2 = (dayChg ?? 0) >= 0;
    const disp = price?.toFixed(2) ?? "—";

    // Bot stats
    const _wr = botStatus?.win_rate ?? botStatus?.account?.win_rate;
    const winRate = typeof _wr === "number" ? _wr * 100 : "—";
    const todayPnl = botStatus?.daily_pnl ?? botStatus?.account?.daily_pnl ?? botStatus?.today_pnl ?? "—";
    const drawdown = botStatus?.drawdown ?? botStatus?.account?.drawdown ?? "—";
    const balance = botStatus?.account_balance ?? botStatus?.account?.account_balance ?? botStatus?.balance ?? "—";
    const tradeCount = botStatus?.total_trades ?? botStatus?.account?.total_trades ?? 0;

    // Signal display — safe number parsing (API returns strings from CSV)
    const sf = v => { const x = parseFloat(v); return isNaN(x) ? "—" : x.toFixed(2); };
    const sigDir = signal?.direction ?? "WAIT";
    const sigConf = signal?.confidence ?? 0;
    const sigEntry = signal?.entry != null ? sf(signal.entry) : (price?.toFixed(2) ?? "—");
    const sigSL = signal?.sl != null ? sf(signal.sl) : "—";
    const sigTP1 = signal?.tp1 != null ? sf(signal.tp1) : "—";
    const sigTP2 = signal?.tp2 != null ? sf(signal.tp2) : "—";
    const sigLot = signal?.lot_size ?? "—";
    const sigRR = signal?.rr ?? "—";
    const sigColor = sigDir === "BUY" ? C.green : sigDir === "SELL" ? C.red : C.muted;

    // Market conditions from signal
    const conditions = marketConds ?? [
        { label: "Trend (EMA200)", value: "—", ok: true },
        { label: "RSI (14)", value: "—", ok: true },
        { label: "Session", value: "—", ok: true },
        { label: "Volatility ATR", value: "—", ok: true },
        { label: "Liquidity Sweep", value: "—", ok: true },
        { label: "News Filter", value: "Clear", ok: true },
    ];

    return (
        <div style={{ background: C.bg, minHeight: "100vh", color: C.text, fontFamily: "'DM Sans',sans-serif" }}>
            <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;600;700&family=DM+Mono:wght@400;500&display=swap');
        *{box-sizing:border-box;margin:0;padding:0}
        ::-webkit-scrollbar{width:3px}::-webkit-scrollbar-thumb{background:#2a2a40;border-radius:3px}
        @keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
        @keyframes fadeUp{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
        @keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(245,197,24,.4)}70%{box-shadow:0 0 0 8px rgba(245,197,24,0)}}
        .card{background:${C.panel};border:1px solid ${C.border};border-radius:12px}
        .fade{animation:fadeUp .3s ease}
      `}</style>

            {/* ── HEADER ── */}
            <div style={{
                background: "#0A0A14", borderBottom: `1px solid ${C.border}`,
                padding: "12px 22px", display: "flex", alignItems: "center", justifyContent: "space-between",
            }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{
                        width: 36, height: 36, borderRadius: 8,
                        background: `linear-gradient(135deg,${C.gold},#A07010)`,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontWeight: 900, fontSize: 16, color: "#060608", fontFamily: "'DM Mono'",
                        animation: "pulse 2.5s infinite",
                    }}>Au</div>
                    <div>
                        <div style={{ fontSize: 14, fontWeight: 700 }}>XAUUSD AI Trader</div>
                        <div style={{ fontSize: 9, color: C.muted, letterSpacing: 2 }}>CLOUD BOT · {GCP_IP} · PAPER MODE</div>
                    </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                    {/* GCP status */}
                    <div style={{
                        background: apiOnline ? `${C.green}12` : `${C.red}12`,
                        border: `1px solid ${apiOnline ? C.green + "40" : C.red + "40"}`,
                        borderRadius: 6, padding: "4px 12px",
                    }}>
                        <div style={{ fontSize: 9, color: C.muted, letterSpacing: 1 }}>GCP SERVER</div>
                        <StatusDot online={apiOnline} />
                    </div>

                    {/* Data source */}
                    <div style={{
                        background: source.includes("✓") ? `${C.green}12` : `${C.gold}12`,
                        border: `1px solid ${source.includes("✓") ? C.green + "40" : C.gold + "40"}`,
                        borderRadius: 6, padding: "4px 10px",
                    }}>
                        <div style={{ fontSize: 9, color: C.muted, letterSpacing: 1 }}>PRICE DATA</div>
                        <div style={{ fontSize: 10, color: source.includes("✓") ? C.green : C.gold, fontFamily: "'DM Mono'" }}>
                            {source}
                        </div>
                    </div>

                    {lastSync && (
                        <div style={{ textAlign: "right" }}>
                            <div style={{ fontSize: 9, color: C.muted, letterSpacing: 1 }}>BOT SYNC</div>
                            <div style={{ fontSize: 11, fontFamily: "'DM Mono'", color: C.text }}>{lastSync}</div>
                        </div>
                    )}
                </div>
            </div>

            <div style={{ padding: "16px 22px", display: "flex", flexDirection: "column", gap: 14 }}>

                {/* ── ROW 1: Price + Stats ── */}
                <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "stretch" }}>

                    {/* Price card */}
                    <div className="card" style={{ padding: "20px 24px", flex: "0 0 auto", minWidth: 310 }}>
                        <div style={{ fontSize: 9, color: C.muted, letterSpacing: 2, marginBottom: 6 }}>GOLD SPOT · XAU/USD</div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                            <div>
                                <div style={{
                                    fontSize: 46, fontWeight: 700, color: C.gold,
                                    fontFamily: "'DM Mono'", letterSpacing: -1, lineHeight: 1, transition: "color .3s",
                                }}>{disp}</div>
                                <div style={{ display: "flex", gap: 16, marginTop: 8 }}>
                                    <div style={{ fontSize: 13, fontFamily: "'DM Mono'", color: isUp ? C.green : C.red }}>
                                        {isUp ? "▲" : "▼"} {Math.abs(delta).toFixed(2)}
                                    </div>
                                    {dayChg !== null && (
                                        <div style={{ fontSize: 13, fontFamily: "'DM Mono'", color: isUp2 ? C.green : C.red }}>
                                            {isUp2 ? "+" : ""}{dayChg?.toFixed(2)} ({isUp2 ? "+" : ""}{dayPct?.toFixed(2)}%)
                                        </div>
                                    )}
                                </div>
                            </div>
                            <Spark data={history} color={isUp ? C.green : C.red} />
                        </div>
                        <div style={{ display: "flex", gap: 20, marginTop: 14, paddingTop: 12, borderTop: `1px solid ${C.border}` }}>
                            {[["OPEN", open?.toFixed(2) ?? "—"], ["HIGH", high?.toFixed(2) ?? "—"], ["LOW", low?.toFixed(2) ?? "—"]].map(([k, v]) => (
                                <div key={k}>
                                    <div style={{ fontSize: 9, color: C.muted, letterSpacing: 1.5 }}>{k}</div>
                                    <div style={{ fontFamily: "'DM Mono'", fontSize: 13, marginTop: 1, color: k === "HIGH" ? C.green : k === "LOW" ? C.red : C.text }}>{v}</div>
                                </div>
                            ))}
                            <div>
                                <div style={{ fontSize: 9, color: C.muted, letterSpacing: 1.5 }}>TRADES</div>
                                <div style={{ fontFamily: "'DM Mono'", fontSize: 13, marginTop: 1, color: C.blue }}>{tradeCount}</div>
                            </div>
                        </div>
                    </div>

                    {/* 4 stat tiles */}
                    {[
                        { l: "Win Rate", v: typeof winRate === "number" ? `${winRate.toFixed(1)}%` : winRate, s: `${tradeCount} trades`, a: C.green },
                        { l: "Today P&L", v: typeof todayPnl === "number" ? `${todayPnl >= 0 ? "+" : ""}$${todayPnl.toFixed(0)}` : todayPnl, s: "paper mode", a: C.gold },
                        { l: "Drawdown", v: typeof drawdown === "number" ? `${drawdown.toFixed(1)}%` : drawdown, s: "Max 20%", a: C.text },
                        { l: "Balance", v: typeof balance === "number" ? `$${balance.toLocaleString()}` : balance, s: "Paper acct", a: C.text },
                    ].map(t => (
                        <div key={t.l} className="card" style={{ padding: "16px 18px", flex: 1, minWidth: 130 }}>
                            <div style={{ fontSize: 9, color: C.muted, letterSpacing: 2, marginBottom: 6 }}>{t.l}</div>
                            <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "'DM Mono'", color: t.a, lineHeight: 1 }}>{t.v}</div>
                            <div style={{ fontSize: 11, color: C.muted, marginTop: 5 }}>{t.s}</div>
                        </div>
                    ))}
                </div>

                {/* ── ROW 2: Signal + Conditions + Log ── */}
                <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "flex-start" }}>

                    {/* AI Signal */}
                    <div className="card" style={{
                        padding: "18px 20px", flex: "0 0 230px",
                        border: `1.5px solid ${sigColor}44`,
                    }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                            <div style={{ fontSize: 9, color: C.muted, letterSpacing: 2 }}>AI TRADE SIGNAL</div>
                            <Ring pct={sigConf} />
                        </div>

                        <div style={{
                            background: `${sigColor}14`, border: `1px solid ${sigColor}33`,
                            borderRadius: 8, padding: "10px", textAlign: "center", marginBottom: 12,
                        }}>
                            <div style={{ color: sigColor, fontSize: 22, fontWeight: 800, letterSpacing: 3 }}>{sigDir}</div>
                            <div style={{ color: C.muted, fontSize: 9, marginTop: 2 }}>XAUUSD · M15 · PAPER</div>
                        </div>

                        {[
                            ["Entry", sigEntry],
                            ["Stop Loss", sigSL],
                            ["TP 1", sigTP1],
                            ["TP 2", sigTP2],
                            ["Lot", sigLot],
                            ["R:R", sigRR],
                        ].map(([k, v]) => (
                            <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", borderBottom: `1px solid ${C.border}` }}>
                                <span style={{ color: C.muted, fontSize: 11 }}>{k}</span>
                                <span style={{ fontFamily: "'DM Mono'", fontSize: 11 }}>{v}</span>
                            </div>
                        ))}
                    </div>

                    {/* Market Conditions */}
                    <div className="card" style={{ padding: "18px 20px", flex: "0 0 210px" }}>
                        <div style={{ fontSize: 9, color: C.muted, letterSpacing: 2, marginBottom: 12 }}>MARKET CONDITIONS</div>
                        {conditions.map((s, i) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "7px 0", borderBottom: `1px solid ${C.border}` }}>
                                <span style={{ color: C.muted, fontSize: 11 }}>{s.label}</span>
                                <span style={{ color: s.ok ? C.green : C.red, fontSize: 11, fontFamily: "'DM Mono'", textAlign: "right" }}>{s.value}</span>
                            </div>
                        ))}
                        <div style={{
                            marginTop: 10, padding: "7px 10px",
                            background: apiOnline ? `${C.green}10` : `${C.gold}10`,
                            border: `1px solid ${apiOnline ? C.green : C.gold}25`, borderRadius: 6,
                        }}>
                            <div style={{ fontSize: 10, color: apiOnline ? C.green : C.gold }}>
                                {apiOnline ? "✓ Live from GCP bot" : "⚡ Waiting for bot data…"}
                            </div>
                        </div>
                    </div>

                    {/* Live Log */}
                    <div className="card" style={{ padding: "18px 20px", flex: 1, minWidth: 240 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                            <div style={{ fontSize: 9, color: C.muted, letterSpacing: 2 }}>SYSTEM LOG</div>
                            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                                <div style={{
                                    width: 6, height: 6, borderRadius: "50%",
                                    background: apiOnline ? C.green : C.muted,
                                    animation: apiOnline ? "blink 1.5s infinite" : "none",
                                }} />
                                <span style={{ fontSize: 9, color: apiOnline ? C.green : C.muted, letterSpacing: 1 }}>
                                    {apiOnline ? "GCP LIVE" : "LOCAL"}
                                </span>
                            </div>
                        </div>
                        <div ref={logRef} style={{ height: 230, overflowY: "auto", display: "flex", flexDirection: "column", gap: 2 }}>
                            {localLog.map((l, i) => (
                                <div key={i} className="fade" style={{ display: "flex", gap: 7, padding: "2px 0" }}>
                                    <span style={{ color: C.muted, fontSize: 9, fontFamily: "'DM Mono'", flexShrink: 0 }}>
                                        {new Date().toTimeString().slice(0, 8)}
                                    </span>
                                    <span style={{
                                        fontFamily: "'DM Mono'", fontSize: 10,
                                        color: l.includes("SIGNAL") || l.includes("✅") ? C.gold
                                            : l.includes("🔴") || l.includes("⚠️") ? C.red
                                                : l.includes("✓") || l.includes("🟢") ? C.green : C.text,
                                    }}>{l}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* ── ROW 3: Trade History ── */}
                <div className="card" style={{ padding: "18px 22px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
                        <div style={{ fontSize: 9, color: C.muted, letterSpacing: 2 }}>TRADE HISTORY</div>
                        <div style={{ fontSize: 9, color: C.muted }}>
                            {apiOnline ? `Live from GCP · ${trades.length} trades` : "Waiting for bot…"}
                        </div>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "50px 55px 1fr 1fr 65px 80px 65px", gap: 8, marginBottom: 8 }}>
                        {["#", "DIR", "ENTRY", "CLOSE", "TIME", "P&L", "STATUS"].map(h => (
                            <div key={h} style={{ fontSize: 9, color: C.muted, letterSpacing: 1.5 }}>{h}</div>
                        ))}
                    </div>
                    {trades.length === 0 ? (
                        <div style={{ textAlign: "center", color: C.muted, fontSize: 12, padding: "20px 0" }}>
                            {apiOnline ? "No trades yet — bot scanning market…" : "Connecting to GCP server…"}
                        </div>
                    ) : (
                        trades.slice(-10).reverse().map((t, i) => {
                            const tf = v => { const x = parseFloat(v); return isNaN(x) ? "—" : x.toFixed(2); };
                            const pnlV = parseFloat(t.pnl); const pnlOk = !isNaN(pnlV);
                            const dir = t.direction || t.dir || "—";
                            return (
                                <div key={i} style={{
                                    display: "grid", gridTemplateColumns: "50px 55px 1fr 1fr 65px 80px 65px",
                                    gap: 8, padding: "8px 0", borderTop: `1px solid ${C.border}`, alignItems: "center",
                                }}>
                                    <span style={{ color: C.muted, fontFamily: "'DM Mono'", fontSize: 11 }}>#{t.ticket ?? i + 1}</span>
                                    <span style={{ color: dir === "BUY" ? C.green : C.red, fontWeight: 700, fontSize: 11, letterSpacing: 1 }}>{dir}</span>
                                    <span style={{ fontFamily: "'DM Mono'", fontSize: 11 }}>{tf(t.entry)}</span>
                                    <span style={{ fontFamily: "'DM Mono'", fontSize: 11 }}>{tf(t.close ?? t.close_price)}</span>
                                    <span style={{ color: C.muted, fontSize: 11 }}>{t.time ?? t.open_time ?? "—"}</span>
                                    <span style={{ fontFamily: "'DM Mono'", fontSize: 11, fontWeight: 700, color: pnlOk && pnlV >= 0 ? C.green : C.red }}>
                                        {pnlOk ? `${pnlV >= 0 ? "+" : ""}$${Math.abs(pnlV).toFixed(0)}` : "—"}
                                    </span>
                                    <span style={{ fontSize: 9, padding: "2px 7px", borderRadius: 4, textAlign: "center", background: `${C.muted}15`, color: C.muted, letterSpacing: .5 }}>
                                        {t.status ?? "closed"}
                                    </span>
                                </div>);
                        })
                    )}
                </div>

                {/* ── FOOTER ── */}
                <div style={{
                    display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8,
                    paddingTop: 4, borderTop: `1px solid ${C.border}40`,
                }}>
                    <div style={{ fontSize: 10, color: C.muted }}>Strategy: Intraday Liquidity · EMA50/200 · RSI · ATR</div>
                    <div style={{ fontSize: 10, color: C.muted, fontFamily: "'DM Mono'" }}>
                        Risk: 1%/trade · Max 0.50 lot · Stop: 3 losses/day · GCP: {GCP_IP}
                    </div>
                    <div style={{ fontSize: 10, color: source.includes("✓") ? C.green : C.gold }}>● {source}</div>
                </div>
            </div>
        </div>
    );
}
