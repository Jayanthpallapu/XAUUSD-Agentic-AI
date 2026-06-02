"use client";

import React, { useState, useEffect, useRef } from "react";
import { 
  TrendingUp, TrendingDown, RefreshCw, AlertTriangle, Bell, Activity, 
  Cpu, Award, ShieldAlert, BookOpen, Send, CheckCircle, Database, Play, PlayCircle
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws");

export default function Dashboard() {
  const [data, setData] = useState({
    agents: [
      { name: "CorrelationAgent", role: "Correlation Analyst", status: "active", accuracy_score: 1.0, total_tasks_completed: 0, total_errors: 0, avg_response_time_ms: 0 },
      { name: "NewsAgent", role: "News Analyst", status: "active", accuracy_score: 1.0, total_tasks_completed: 0, total_errors: 0, avg_response_time_ms: 0 },
      { name: "TradingAgent", role: "Signal Generator", status: "active", accuracy_score: 1.0, total_tasks_completed: 0, total_errors: 0, avg_response_time_ms: 0 },
      { name: "QAAgent", role: "QA Audit Analyst", status: "active", accuracy_score: 1.0, total_tasks_completed: 0, total_errors: 0, avg_response_time_ms: 0 },
      { name: "PerformanceAgent", role: "Performance Tracker", status: "active", accuracy_score: 1.0, total_tasks_completed: 0, total_errors: 0, avg_response_time_ms: 0 },
      { name: "SupervisorAgent", role: "System Supervisor", status: "active", accuracy_score: 1.0, total_tasks_completed: 0, total_errors: 0, avg_response_time_ms: 0 }
    ],
    metrics: {
      win_rate: 66.7,
      total_pnl: 480.00,
      active_positions_count: 1,
      total_cycles_count: 3,
      confluence_score: 75.0
    },
    active_trades: [
      { id: "t-1", direction: "BUY", entry_price: 2645.50, stop_loss: 2635.00, take_profit: 2665.00, confidence_score: 0.85, reasoning: "Strong confluence of falling Dollar Index (DXY) and positive gold spot buying pressure.", status: "active", opened_at: new Date().toISOString() }
    ],
    latest_correlation: {
      pair_correlations: [
        { pair: "DXY (Dollar Index)", correlation_score: -0.85, trend: "bearish", impact_on_gold: "Falling DXY is bullish for dollar-denominated Gold spot prices." },
        { pair: "US10Y Yields", correlation_score: -0.72, trend: "bearish", impact_on_gold: "Declining yields represent falling opportunity cost, stimulating gold purchases." },
        { pair: "EUR/USD", correlation_score: 0.82, trend: "bullish", impact_on_gold: "EURUSD strength mirrors DXY weakness, validating gold bullishness." },
        { pair: "Silver (XAGUSD)", correlation_score: 0.91, trend: "bullish", impact_on_gold: "Strong positive metals trend aligns with gold moves." }
      ],
      news_impacts: [
        { headline: "US Treasury Yields Drop Below Key Support", source: "Bloomberg", sentiment: "bullish", impact_score: 7.5 }
      ],
      overall_confluence_score: 75.0,
      summary: "Macro correlation indicators are strongly bullish. Dollar Index is breaking down beneath 104.5 level, EURUSD rallies, and yields decline. Metal baskets trend upward."
    },
    latest_news: {
      news_items: [
        { title: "Geopolitical tensions spur safe-haven gold demand in European trading session", source: "Google News", url: "#", sentiment: "bullish", impact_level: "high" },
        { title: "Fed Governors signal data-dependent stance on upcoming June interest rate decision", source: "Investing.com", url: "#", sentiment: "neutral", impact_level: "medium" },
        { title: "Central Bank gold buying continues at robust pace according to quarterly updates", source: "Bloomberg", url: "#", sentiment: "bullish", impact_level: "high" }
      ],
      market_sentiment: "bullish",
      impact_on_pairs: [
        { pair: "EURUSD", expected_impact: "Expected consolidation or mild rally" },
        { pair: "USDJPY", expected_impact: "Bearish pressure due to safe-haven Yen inflows" }
      ],
      is_high_impact: true,
      summary: "Broad safe-haven inflows driven by geopolitical developments and expectation of rate softening maintain bullish posture."
    },
    latest_performance: {
      win_rate: 66.7,
      total_pnl: 480.0,
      sharpe_ratio: 2.1,
      max_drawdown: 1.5,
      profit_factor: 2.8,
      total_trades: 3,
      winning_trades: 2,
      losing_trades: 1,
      agent_scores: { "CorrelationAgent": 0.95, "NewsAgent": 0.92, "TradingAgent": 0.88, "QAAgent": 0.98 }
    },
    latest_supervisor: {
      agent_statuses: [
        { agent: "CorrelationAgent", status: "active", health_score: 1.0 },
        { agent: "NewsAgent", status: "active", health_score: 0.98 },
        { agent: "TradingAgent", status: "active", health_score: 0.95 }
      ],
      actions_taken: [
        { action: "LOG_LESSON", target_agent: "TradingAgent", reason: "Incorrect risk/reward ratio configuration", result: "Saved lesson, updated accuracy rating" }
      ],
      daily_summary: "Crew running optimal loops. Successfully executed 3 analysis cycles. Completed 1 paper trade win and queued 1 active buy position. Dynamic training lessons injected.",
      telegram_sent: true
    },
    notifications: [
      { id: "n-1", level: "critical", title: "Breaking News: Geopolitical safe-haven demand spike", message: "European market developments trigger large gold purchasing inflows. Spot price rises $18.", source_agent: "NewsAgent", created_at: new Date().toISOString() },
      { id: "n-2", level: "info", title: "Daily Telegram Performance Summary Transmitted", message: "Successfully sent daily performance update to channel members.", source_agent: "SupervisorAgent", created_at: new Date(Date.now() - 100000).toISOString() }
    ]
  });

  const [logs, setLogs] = useState([
    "SupervisorAgent: Running scheduled agent nodes diagnostics...",
    "System: Main connection online.",
    "CorrelationAgent: Successfully parsed Twelve Data forex rates.",
    "NewsAgent: Fetched Google News RSS. Found 3 key gold sentiment articles.",
    "TradingAgent: Evaluated confluence metrics. Generating paper trade BUY position...",
    "QAAgent: Audited TradingAgent signal. Risk/Reward verified at 1:2.0. APPROVED.",
    "PerformanceAgent: Complied trade metrics. Win rate: 66.7%.",
    "SupervisorAgent: Dynamic feedback lessons successfully injected to active agent nodes."
  ]);

  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [goldPrice, setGoldPrice] = useState(2645.50);
  const [wsStatus, setWsStatus] = useState("offline");
  const logsEndRef = useRef(null);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Simulate Gold price changes live
  useEffect(() => {
    const interval = setInterval(() => {
      setGoldPrice(prev => {
        const change = (Math.random() - 0.48) * 1.5;
        return parseFloat((prev + change).toFixed(2));
      });
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  // API integration: polling & websocket
  useEffect(() => {
    // 1. Fetch dashboard data
    const fetchDashboard = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/dashboard`);
        if (res.ok) {
          const apiData = await res.json();
          setData(apiData);
        }
      } catch (err) {
        console.log("Could not connect to FastAPI server. Displaying high-fidelity mock data.");
      }
    };
    
    fetchDashboard();
    const pollInterval = setInterval(fetchDashboard, 15000);

    // 2. Connect WebSocket for live logs
    let ws;
    const connectWs = () => {
      ws = new WebSocket(`${WS_BASE_URL}/ws/live`);
      
      ws.onopen = () => {
        setWsStatus("connected");
        console.log("WebSocket connected to FastAPI stream.");
      };
      
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "log") {
            setLogs(prev => [...prev.slice(-99), msg.message]);
          } else if (msg.type === "status") {
            // Update dashboard metrics on updates
            fetchDashboard();
          }
        } catch (e) {
          setLogs(prev => [...prev.slice(-99), `Raw Message: ${event.data}`]);
        }
      };

      ws.onclose = () => {
        setWsStatus("offline");
        setTimeout(connectWs, 5000); // Reconnect
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connectWs();

    return () => {
      clearInterval(pollInterval);
      if (ws) ws.close();
    };
  }, []);

  const triggerCycle = async () => {
    setLoading(true);
    setLogs(prev => [...prev, "System: Dispatching manual analysis cycle request..."]);
    try {
      const res = await fetch(`${API_BASE_URL}/api/trigger-cycle`, { method: "POST" });
      if (res.ok) {
        setLogs(prev => [...prev, "System: Manual cycle successfully dispatched to FastAPI background task queue."]);
      } else {
        throw new Error("Trigger request failed.");
      }
    } catch (err) {
      setLogs(prev => [
        ...prev, 
        "System [Demo Mode]: Simulating market analysis cycle run...",
        "CorrelationAgent: Scanning indices... DXY Bearish. US10Y Bearish.",
        "NewsAgent: Analyzing inflation expectations... Bullish bias.",
        "TradingAgent: Spot gold price analyzed. Confluence high.",
        "QAAgent: Audited signal. Approved.",
        "SupervisorAgent: Cycle complete. Telegram notification dispatched."
      ]);
    }
    setTimeout(() => setLoading(false), 2000);
  };

  const restartAgent = async (name) => {
    setLogs(prev => [...prev, `SupervisorAgent: Attempting restart on agent node '${name}'...`]);
    try {
      const res = await fetch(`${API_BASE_URL}/api/agents/${name}/restart`, { method: "POST" });
      if (res.ok) {
        setLogs(prev => [...prev, `SupervisorAgent: Node '${name}' reset successfully.`]);
      }
    } catch (err) {
      setLogs(prev => [...prev, `SupervisorAgent [Demo Mode]: Successfully reset agent '${name}' status and cleared errors.`]);
      setData(prev => ({
        ...prev,
        agents: prev.agents.map(ag => ag.name === name ? { ...ag, status: "active", total_errors: 0 } : ag)
      }));
    }
  };

  const currentPnL = data.active_trades.reduce((sum, t) => {
    if (t.direction === "BUY") {
      return sum + (goldPrice - t.entry_price) * 50;
    } else if (t.direction === "SELL") {
      return sum + (t.entry_price - goldPrice) * 50;
    }
    return sum;
  }, 0);

  return (
    <div className="min-h-screen bg-[#0a0c14] text-slate-100 font-sans flex overflow-hidden">
      
      {/* SIDE NAV PANEL */}
      <aside className="w-64 bg-[#10121d] border-r border-slate-800 flex flex-col justify-between shrink-0">
        <div>
          {/* Company Brand Logo */}
          <div className="h-16 flex items-center px-6 gap-3 border-b border-slate-800 bg-[#0c0e16]">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-amber-500 to-yellow-300 flex items-center justify-center font-bold text-slate-900 text-lg shadow-lg shadow-amber-500/20">
              Au
            </div>
            <div>
              <h1 className="font-bold text-sm tracking-wider text-amber-400">ANTIGRAVITY</h1>
              <p className="text-[10px] text-slate-500 font-mono">XAUUSD AGENTIC CO.</p>
            </div>
          </div>

          <div className="p-4 border-b border-slate-800 bg-slate-900/10">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-slate-500">SPOT GOLD PRICE</span>
              <span className="animate-pulse flex items-center gap-1 text-[10px] text-green-400 font-mono">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400"></span> LIVE
              </span>
            </div>
            <div className="text-2xl font-bold text-amber-300 font-mono tracking-tight">
              ${goldPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>

          <nav className="p-4 space-y-1.5">
            <button 
              onClick={() => setActiveTab("dashboard")} 
              className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-semibold tracking-wide transition-all ${activeTab === "dashboard" ? "bg-amber-500/10 text-amber-400 border-l-2 border-amber-500" : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"}`}
            >
              <Cpu className="w-4 h-4" /> Agentic Dashboard
            </button>
            <button 
              onClick={() => setActiveTab("trades")} 
              className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-semibold tracking-wide transition-all ${activeTab === "trades" ? "bg-amber-500/10 text-amber-400 border-l-2 border-amber-500" : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"}`}
            >
              <TrendingUp className="w-4 h-4" /> Paper Trading Signals
            </button>
            <button 
              onClick={() => setActiveTab("knowledge")} 
              className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg text-xs font-semibold tracking-wide transition-all ${activeTab === "knowledge" ? "bg-amber-500/10 text-amber-400 border-l-2 border-amber-500" : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"}`}
            >
              <BookOpen className="w-4 h-4" /> Supervisor Memory
            </button>
          </nav>
        </div>

        {/* WebSocket Connect Panel */}
        <div className="p-4 border-t border-slate-800 bg-[#0d0e16]">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500 font-mono">BACKEND API:</span>
            <span className={`px-2 py-0.5 rounded-full text-[9px] font-mono font-bold ${wsStatus === "connected" ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
              {wsStatus.toUpperCase()}
            </span>
          </div>
        </div>
      </aside>

      {/* MAIN CONTENT VIEWPORT */}
      <main className="flex-1 flex flex-col overflow-hidden bg-[#0a0b12]">
        
        {/* TOP STATUS BAR */}
        <header className="h-16 border-b border-slate-800 flex items-center justify-between px-8 bg-[#10121d] shrink-0">
          <div className="flex items-center gap-4">
            <span className="text-slate-400 text-xs font-mono uppercase tracking-widest">{activeTab} panel</span>
          </div>
          
          <div className="flex items-center gap-3">
            <button 
              onClick={triggerCycle} 
              disabled={loading} 
              className="flex items-center gap-2 bg-gradient-to-r from-amber-500 to-yellow-400 hover:from-amber-600 hover:to-yellow-500 text-slate-900 text-xs font-extrabold px-4 py-2 rounded-lg transition-all shadow-lg shadow-amber-500/10 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> 
              {loading ? "PROCESSING..." : "TRIGGER ANALYSIS CYCLE"}
            </button>
          </div>
        </header>

        {/* SCROLLABLE CENTRAL CONTAINER */}
        <div className="flex-1 overflow-y-auto p-8 space-y-6">
          
          {/* NEWS ALERT TOP BANNER */}
          {data.latest_news?.is_high_impact && (
            <div className="bg-gradient-to-r from-red-950/40 via-red-900/10 to-transparent border border-red-900/60 p-4 rounded-xl flex items-start gap-3 shadow-md shadow-red-950/10">
              <ShieldAlert className="w-5 h-5 text-red-400 shrink-0 mt-0.5 animate-bounce" />
              <div>
                <h3 className="text-xs font-bold text-red-400 uppercase tracking-wider">High-Impact News Flash Released!</h3>
                <p className="text-slate-300 text-xs mt-1 leading-relaxed">
                  {data.latest_news.summary}
                </p>
              </div>
            </div>
          )}

          {activeTab === "dashboard" && (
            <>
              {/* CORE METRICS GRID */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
                <div className="bg-gradient-to-tr from-[#141624] to-[#121420] border border-slate-800 p-5 rounded-xl flex flex-col justify-between hover:border-slate-700/80 transition-all">
                  <span className="text-xs text-slate-500 font-semibold tracking-wide uppercase">Total Net Profit</span>
                  <div className="mt-2 flex items-baseline gap-2">
                    <span className={`text-2xl font-bold font-mono tracking-tight ${data.metrics.total_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                      ${(data.metrics.total_pnl + currentPnL).toFixed(2)}
                    </span>
                    <span className="text-xs text-slate-400">USD</span>
                  </div>
                  <div className="text-[10px] text-slate-400 mt-2 font-mono flex items-center gap-1">
                    <Database className="w-3 h-3 text-slate-500" /> Paper Account Balance: $10,000.00
                  </div>
                </div>

                <div className="bg-gradient-to-tr from-[#141624] to-[#121420] border border-slate-800 p-5 rounded-xl flex flex-col justify-between hover:border-slate-700/80 transition-all">
                  <span className="text-xs text-slate-500 font-semibold tracking-wide uppercase">Paper Win Rate</span>
                  <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-2xl font-bold font-mono tracking-tight text-amber-400">{data.metrics.win_rate}%</span>
                  </div>
                  <div className="text-[10px] text-slate-400 mt-2 font-mono">
                    Based on {data.latest_performance?.total_trades || 0} closed signal runs
                  </div>
                </div>

                <div className="bg-gradient-to-tr from-[#141624] to-[#121420] border border-slate-800 p-5 rounded-xl flex flex-col justify-between hover:border-slate-700/80 transition-all">
                  <span className="text-xs text-slate-500 font-semibold tracking-wide uppercase">Cycles Evaluated</span>
                  <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-2xl font-bold font-mono tracking-tight text-cyan-400">{data.metrics.total_cycles_count}</span>
                  </div>
                  <div className="text-[10px] text-slate-400 mt-2 font-mono">
                    24/5 Automated CRON scheduler online
                  </div>
                </div>

                <div className="bg-gradient-to-tr from-[#141624] to-[#121420] border border-slate-800 p-5 rounded-xl flex flex-col justify-between hover:border-slate-700/80 transition-all">
                  <span className="text-xs text-slate-500 font-semibold tracking-wide uppercase">Confluence Score</span>
                  <div className="mt-2 flex items-center justify-between">
                    <span className="text-2xl font-bold font-mono tracking-tight text-emerald-400">{data.metrics.confluence_score} / 100</span>
                    <div className="w-12 h-6 bg-slate-800 rounded-full overflow-hidden flex relative items-center justify-center text-[10px] font-bold">
                      <div className="absolute inset-0 bg-emerald-500/20" style={{ width: `${data.metrics.confluence_score}%` }}></div>
                      <span className="relative z-10 text-[9px] text-emerald-400">HIGH</span>
                    </div>
                  </div>
                  <div className="text-[10px] text-slate-400 mt-2 font-mono">
                    Aggregated across all macro markers
                  </div>
                </div>
              </div>

              {/* AGENTS SYSTEM WORKPLACE GRID */}
              <div className="space-y-4">
                <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-amber-500" /> Active AI Agentic Crew Node Status
                </h2>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                  {data.agents.map((agent, i) => (
                    <div key={i} className="bg-gradient-to-b from-[#141724] to-[#11131e] border border-slate-800/80 p-5 rounded-xl relative hover:border-slate-700 transition-all">
                      <div className="flex justify-between items-start">
                        <div>
                          <h3 className="font-bold text-xs text-slate-200">{agent.name}</h3>
                          <p className="text-[10px] text-slate-500 font-mono mt-0.5">{agent.role}</p>
                        </div>
                        <span className={`px-2 py-0.5 rounded-full text-[9px] font-mono font-bold uppercase ${agent.status === "active" ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
                          {agent.status}
                        </span>
                      </div>

                      <div className="mt-4 grid grid-cols-2 gap-2 border-t border-slate-800/60 pt-3 text-[10px] font-mono text-slate-400">
                        <div>Tasks Completed: <span className="text-slate-200 font-bold">{agent.total_tasks_completed}</span></div>
                        <div>Errors: <span className="text-slate-200 font-bold">{agent.total_errors}</span></div>
                        <div>Response Time: <span className="text-slate-200 font-bold">{agent.avg_response_time_ms ? `${agent.avg_response_time_ms.toFixed(0)}ms` : "N/A"}</span></div>
                        <div>Accuracy Rating: <span className="text-amber-400 font-bold">{(agent.accuracy_score * 100).toFixed(0)}%</span></div>
                      </div>

                      {agent.status === "error" && (
                        <div className="absolute inset-0 bg-[#0b0c13]/90 backdrop-blur-sm rounded-xl flex flex-col items-center justify-center p-4 text-center">
                          <AlertTriangle className="w-7 h-7 text-red-400 animate-pulse mb-1" />
                          <h4 className="text-xs font-bold text-red-400">Node Failure Detected</h4>
                          <button 
                            onClick={() => restartAgent(agent.name)}
                            className="mt-3 bg-red-500/10 border border-red-500/40 text-red-400 hover:bg-red-500/20 text-[10px] font-bold px-3 py-1 rounded transition-all"
                          >
                            RESTART NODE
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* CORE DASHBOARD ROW 2: ACTIVE TRADES AND NEWS SENTIMENT */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                
                {/* ACTIVE TRADES */}
                <div className="bg-[#10121d] border border-slate-800/80 p-5 rounded-xl space-y-4 flex flex-col justify-between">
                  <div>
                    <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center justify-between">
                      <span>Live Paper Positions</span>
                      <span className="text-[10px] text-slate-500 font-mono uppercase tracking-normal">Size: 0.5 Lots</span>
                    </h2>
                    
                    {data.active_trades.length === 0 ? (
                      <div className="py-12 text-center text-xs text-slate-500 font-mono">
                        No active simulated positions currently. Trigger cycle to scan.
                      </div>
                    ) : (
                      data.active_trades.map((trade, i) => {
                        const tradePnL = trade.direction === "BUY" 
                          ? (goldPrice - trade.entry_price) * 50
                          : (trade.entry_price - goldPrice) * 50;

                        return (
                          <div key={i} className="border border-slate-800 bg-[#0d0e16]/80 p-4 rounded-lg space-y-3">
                            <div className="flex justify-between items-center">
                              <span className={`px-2 py-0.5 rounded text-[10px] font-bold font-mono ${trade.direction === "BUY" ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
                                {trade.direction}
                              </span>
                              <span className={`font-mono text-sm font-bold ${tradePnL >= 0 ? "text-green-400" : "text-red-400"}`}>
                                {tradePnL >= 0 ? "+" : ""}${tradePnL.toFixed(2)} USD
                              </span>
                            </div>
                            
                            <div className="grid grid-cols-3 text-[10px] font-mono text-slate-400 gap-1 pt-1 border-t border-slate-800/60">
                              <div>Entry: <span className="text-slate-200">${trade.entry_price.toFixed(2)}</span></div>
                              <div>Stop Loss: <span className="text-red-400">${trade.stop_loss.toFixed(2)}</span></div>
                              <div>Take Profit: <span className="text-green-400">${trade.take_profit.toFixed(2)}</span></div>
                            </div>
                            
                            <p className="text-[10px] text-slate-400 italic font-mono leading-relaxed pt-1 border-t border-slate-800/40">
                              "{trade.reasoning}"
                            </p>
                          </div>
                        );
                      })
                    )}
                  </div>
                  
                  {/* Historical win rate visual curves */}
                  <div className="pt-4 border-t border-slate-800/80">
                    <span className="text-[10px] text-slate-500 font-semibold tracking-wider uppercase block mb-2">Simulated Equity Curve (Past 5 cycles)</span>
                    <div className="h-24 w-full bg-slate-900/50 rounded-lg p-2 flex items-end">
                      <svg className="w-full h-full" viewBox="0 0 100 30" preserveAspectRatio="none">
                        <path 
                          d="M 0,25 L 20,22 L 40,24 L 60,15 L 80,10 L 100,5" 
                          fill="none" 
                          stroke="rgba(245, 158, 11, 0.4)" 
                          strokeWidth="1"
                        />
                        <path 
                          d="M 0,25 L 20,22 L 40,24 L 60,15 L 80,10 L 100,5 L 100,30 L 0,30 Z" 
                          fill="url(#goldGradient)" 
                          opacity="0.1"
                        />
                        <defs>
                          <linearGradient id="goldGradient" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#f59e0b" />
                            <stop offset="100%" stopColor="#0a0c14" />
                          </linearGradient>
                        </defs>
                        {/* Circles at keys */}
                        <circle cx="0" cy="25" r="1.5" fill="#f59e0b" />
                        <circle cx="20" cy="22" r="1.5" fill="#f59e0b" />
                        <circle cx="40" cy="24" r="1.5" fill="#f59e0b" />
                        <circle cx="60" cy="15" r="1.5" fill="#f59e0b" />
                        <circle cx="80" cy="10" r="1.5" fill="#f59e0b" />
                        <circle cx="100" cy="5" r="1.5" fill="#f59e0b" />
                      </svg>
                    </div>
                  </div>
                </div>

                {/* CORRELATIONS & NEWS IMPACTS */}
                <div className="bg-[#10121d] border border-slate-800/80 p-5 rounded-xl space-y-4">
                  <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                    <span>Correlated Forex & Commodity Pairs Sentiment</span>
                    <span className="text-[9px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 font-mono">BULLISH BIAS</span>
                  </h2>

                  {data.latest_correlation ? (
                    <div className="space-y-3">
                      <div className="space-y-2 max-h-48 overflow-y-auto">
                        {data.latest_correlation.pair_correlations.map((pair, i) => (
                          <div key={i} className="flex justify-between items-center text-xs p-2 rounded bg-slate-900/30 border border-slate-800/60">
                            <div>
                              <span className="font-bold text-slate-300">{pair.pair}</span>
                              <span className="text-[10px] text-slate-500 font-mono ml-2">Corr: {pair.correlation_score}</span>
                            </div>
                            <span className={`px-2 py-0.5 rounded text-[9px] font-mono font-bold uppercase ${pair.trend === "bullish" ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
                              {pair.trend}
                            </span>
                          </div>
                        ))}
                      </div>
                      <p className="text-[11px] font-mono text-slate-400 bg-slate-900/20 p-3 rounded-lg border border-slate-800/40 leading-relaxed italic">
                        "{data.latest_correlation.summary}"
                      </p>
                    </div>
                  ) : (
                    <div className="py-12 text-center text-xs text-slate-500 font-mono">
                      No correlation scans executed yet.
                    </div>
                  )}
                </div>

              </div>

              {/* CORE DASHBOARD ROW 3: WEBSOCKET LIVE STREAMING LOGS FEED */}
              <div className="bg-[#10121d] border border-slate-800/80 rounded-xl overflow-hidden flex flex-col h-96">
                <div className="h-12 border-b border-slate-800 flex items-center justify-between px-6 bg-[#0c0e16]">
                  <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-cyan-400 animate-pulse" /> Live Agentic Crew Thinking Stream
                  </h2>
                  <span className="text-[9px] text-slate-500 font-mono">WEBSOCKET PIPELINE</span>
                </div>
                
                <div className="flex-1 p-6 overflow-y-auto font-mono text-xs space-y-2 bg-[#090b12] text-slate-300">
                  {logs.map((log, index) => (
                    <div key={index} className="flex gap-2 items-start py-0.5 leading-relaxed">
                      <span className="text-slate-600 select-none" suppressHydrationWarning>[{new Date().toLocaleTimeString()}]</span>
                      <span className={
                        log.startsWith("SupervisorAgent:") ? "text-amber-300" :
                        log.startsWith("TradingAgent:") ? "text-green-400 font-semibold" :
                        log.startsWith("QAAgent:") ? "text-emerald-400" :
                        log.startsWith("System:") ? "text-cyan-400 font-bold" : "text-slate-300"
                      }>
                        {log}
                      </span>
                    </div>
                  ))}
                  <div ref={logsEndRef} />
                </div>
              </div>
            </>
          )}

          {activeTab === "trades" && (
            <div className="bg-[#10121d] border border-slate-800 rounded-xl p-6 space-y-6">
              <div className="flex justify-between items-center">
                <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300">Simulated Paper Trading Book</h2>
                <span className="text-[10px] text-slate-500 font-mono">STARTING BALANCE: $10,000.00 USD</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400 font-semibold uppercase tracking-wider font-mono">
                      <th className="pb-3">Trade ID</th>
                      <th className="pb-3">Symbol</th>
                      <th className="pb-3">Type</th>
                      <th className="pb-3">Entry Price</th>
                      <th className="pb-3">Stop Loss</th>
                      <th className="pb-3">Take Profit</th>
                      <th className="pb-3">PnL (USD)</th>
                      <th className="pb-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                    <tr className="hover:bg-slate-900/10">
                      <td className="py-4 font-bold text-amber-500">t-1</td>
                      <td className="py-4">XAUUSD</td>
                      <td className="py-4 text-green-400 font-bold">BUY</td>
                      <td className="py-4">$2,645.50</td>
                      <td className="py-4 text-slate-500">$2,635.00</td>
                      <td className="py-4 text-slate-500">$2,665.00</td>
                      <td className={`py-4 font-bold ${goldPrice >= 2645.50 ? "text-green-400" : "text-red-400"}`}>
                        {(goldPrice - 2645.50) >= 0 ? "+" : ""}${((goldPrice - 2645.50) * 50).toFixed(2)}
                      </td>
                      <td className="py-4"><span className="px-2 py-0.5 bg-green-500/10 text-green-400 rounded-full font-bold">ACTIVE</span></td>
                    </tr>
                    <tr className="hover:bg-slate-900/10">
                      <td className="py-4 font-bold text-slate-500">t-2</td>
                      <td className="py-4">XAUUSD</td>
                      <td className="py-4 text-green-400 font-bold">BUY</td>
                      <td className="py-4">$2,630.00</td>
                      <td className="py-4 text-slate-500">$2,620.00</td>
                      <td className="py-4 text-slate-500">$2,650.00</td>
                      <td className="py-4 text-green-400 font-bold">+$1,000.00</td>
                      <td className="py-4"><span className="px-2 py-0.5 bg-slate-800 text-slate-400 rounded-full font-bold">WIN</span></td>
                    </tr>
                    <tr className="hover:bg-slate-900/10">
                      <td className="py-4 font-bold text-slate-500">t-3</td>
                      <td className="py-4">XAUUSD</td>
                      <td className="py-4 text-red-400 font-bold">SELL</td>
                      <td className="py-4">$2,652.00</td>
                      <td className="py-4 text-slate-500">$2,662.00</td>
                      <td className="py-4 text-slate-500">$2,632.00</td>
                      <td className="py-4 text-red-400 font-bold">-$500.00</td>
                      <td className="py-4"><span className="px-2 py-0.5 bg-slate-800 text-slate-400 rounded-full font-bold">LOSS</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === "knowledge" && (
            <div className="space-y-6">
              
              {/* SUPERVISOR STATS */}
              <div className="bg-[#10121d] border border-slate-800 rounded-xl p-6 space-y-4">
                <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                  <Award className="w-5 h-5 text-amber-400" /> Dynamic Learning Backstories (Agent Memory Backfill)
                </h2>
                <p className="text-xs text-slate-400 leading-relaxed max-w-3xl">
                  Lessons learned are generated during supervisor audits when QA flags issues or closed trades hit SL limits. 
                  These records are injected directly into each agent's system prompt backstory on initialization, forcing them to learn from past mistakes.
                </p>
                
                <div className="divide-y divide-slate-800/60 font-mono text-xs">
                  <div className="py-4 space-y-1.5">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-amber-300">CorrelationAgent Memory Log</span>
                      <span className="text-[10px] text-slate-500">2026-06-02 18:45:00 UTC</span>
                    </div>
                    <p className="text-slate-300"><span className="text-slate-500">Mistake:</span> Underestimated inverse US Dollar Index correlation strength during inflation runs.</p>
                    <p className="text-slate-400"><span className="text-slate-500">Correction/Lesson:</span> Correlate price shifts with DXY. A DXY rise above 104.8 triggers bearish gold bias. Gold price is heavily inversely correlated to the DXY.</p>
                  </div>
                  <div className="py-4 space-y-1.5">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-amber-300">TradingAgent Memory Log</span>
                      <span className="text-[10px] text-slate-500">2026-06-02 18:50:00 UTC</span>
                    </div>
                    <p className="text-slate-300"><span className="text-slate-500">Mistake:</span> Placed BUY position during a strong US10Y yields breakout, leading to stop loss hit.</p>
                    <p className="text-slate-400"><span className="text-slate-500">Correction/Lesson:</span> Never buy gold if yields break out. Yields breakout represents severe opportunity cost for non-yielding gold, forcing institutional sells.</p>
                  </div>
                  <div className="py-4 space-y-1.5">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-amber-300">NewsAgent Memory Log</span>
                      <span className="text-[10px] text-slate-500">2026-06-02 18:55:00 UTC</span>
                    </div>
                    <p className="text-slate-300"><span className="text-slate-500">Mistake:</span> Classified minor speech events as high-impact calendar, triggering warning spams.</p>
                    <p className="text-slate-400"><span className="text-slate-500">Correction/Lesson:</span> Inspect economic calendar ratings first. Only FOMC Chair Powell speech, NFP, CPI and rate changes are high impact.</p>
                  </div>
                </div>
              </div>

              {/* SUPERVISOR AUDIT NOTES */}
              <div className="bg-[#10121d] border border-slate-800 rounded-xl p-6">
                <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300 mb-4">Latest Supervisor Audit Logs</h2>
                <div className="p-4 rounded-lg bg-[#0d0e16]/80 border border-slate-800 text-xs font-mono leading-relaxed text-slate-300">
                  <p className="font-bold text-amber-400 uppercase tracking-widest mb-2 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-amber-400" /> DAILY SUPERVISOR REPORT
                  </p>
                  <p className="text-slate-400 mb-4">{new Date().toISOString()} | TRANSMITTED TO TELEGRAM CHANNEL</p>
                  <p className="italic">
                    "{data.latest_supervisor.daily_summary}"
                  </p>
                  <div className="mt-4 pt-3 border-t border-slate-800 text-slate-400">
                    Active corrections: restart actions executed ({data.latest_supervisor.actions_taken.length}), health diagnostics verified.
                  </div>
                </div>
              </div>

            </div>
          )}

        </div>
      </main>

    </div>
  );
}
