import { useEffect, useRef, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { SimulationSocket } from '@/lib/websocket';
import { useSimulationLiveStore } from '@/store/simulation';
import { TERMINAL_STATUSES } from '@/lib/constants';
import api from '@/lib/api';

const PLATFORM_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  Twitter:   { bg: 'bg-[#5B5FEE]/15', text: 'text-[#5B5FEE]',  dot: '#5B5FEE' },
  Reddit:    { bg: 'bg-[#00D4FF]/15', text: 'text-[#00D4FF]',  dot: '#00D4FF' },
  TikTok:    { bg: 'bg-[#A78BFA]/15', text: 'text-[#A78BFA]',  dot: '#A78BFA' },
  Instagram: { bg: 'bg-[#A78BFA]/15', text: 'text-[#A78BFA]',  dot: '#A78BFA' },
  Facebook:  { bg: 'bg-[#5B5FEE]/15', text: 'text-[#5B5FEE]',  dot: '#5B5FEE' },
  LinkedIn:  { bg: 'bg-[#00D4FF]/15', text: 'text-[#00D4FF]',  dot: '#00D4FF' },
  YouTube:   { bg: 'bg-[#EF4444]/15', text: 'text-[#EF4444]',  dot: '#EF4444' },
};

function sentimentColor(score: number | null): string {
  if (score === null) return '#64748B';
  if (score >= 0.3)  return '#10B981';
  if (score <= -0.3) return '#EF4444';
  return '#F59E0B';
}

/* ── Mini SVG Sentiment Timeline ── */
function SentimentTimeline({ events }: { events: { sentiment_score?: number | null }[] }) {
  const scores = useMemo(() => {
    const filtered = events
      .filter((e) => e.sentiment_score != null)
      .map((e) => e.sentiment_score as number);
    return filtered.slice(-80); // keep last 80 points
  }, [events]);

  if (scores.length < 2) {
    return (
      <div className="w-full h-full flex items-center justify-center">
        <p className="text-[11px] text-saibyl-muted font-mono">Waiting for sentiment data...</p>
      </div>
    );
  }

  const W = 800;
  const H = 64;
  const pad = 4;

  const xStep = (W - pad * 2) / (scores.length - 1);
  const toY = (s: number) => pad + ((1 - (s + 1) / 2) * (H - pad * 2));

  const pathD = scores
    .map((s, i) => `${i === 0 ? 'M' : 'L'} ${(pad + i * xStep).toFixed(1)} ${toY(s).toFixed(1)}`)
    .join(' ');

  const fillD = `${pathD} L ${(pad + (scores.length - 1) * xStep).toFixed(1)} ${H} L ${pad} ${H} Z`;

  const lastScore = scores[scores.length - 1];
  const lineColor = sentimentColor(lastScore);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="w-full h-full"
    >
      {/* Zero line */}
      <line x1={pad} y1={H / 2} x2={W - pad} y2={H / 2} stroke="rgba(255,255,255,0.06)" strokeWidth="1" strokeDasharray="4 4" />

      {/* Fill under curve */}
      <defs>
        <linearGradient id="sgrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={lineColor} stopOpacity="0.25" />
          <stop offset="100%" stopColor={lineColor} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={fillD} fill="url(#sgrad)" />

      {/* Line */}
      <path d={pathD} fill="none" stroke={lineColor} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />

      {/* Last dot */}
      <circle
        cx={(pad + (scores.length - 1) * xStep).toFixed(1)}
        cy={toY(lastScore).toFixed(1)}
        r="3"
        fill={lineColor}
      />
    </svg>
  );
}

/* ── Event Card ── */
function EventCard({ evt }: { evt: any }) {
  const platform = evt.platform as string | undefined;
  const style = platform ? PLATFORM_STYLES[platform] : null;
  const score = evt.sentiment_score as number | null | undefined;

  return (
    <motion.div
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.18 }}
      className="rounded-xl bg-white/[0.03] border border-white/[0.04] p-3 text-xs"
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-medium text-saibyl-platinum text-[12px] truncate max-w-[120px]">
          {evt.agent_username || evt.event_type}
        </span>
        {platform && style && (
          <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono ${style.bg} ${style.text}`}>
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: style.dot }} />
            {platform}
          </span>
        )}
      </div>
      {evt.content && (
        <p className="text-saibyl-muted text-[11px] leading-relaxed line-clamp-2 mb-1.5">{evt.content}</p>
      )}
      {score != null && (
        <div className="flex items-center gap-1.5">
          <div className="flex-1 h-1 bg-white/[0.06] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all"
              style={{ width: `${((score + 1) / 2) * 100}%`, background: sentimentColor(score) }}
            />
          </div>
          <span className="font-mono text-[10px]" style={{ color: sentimentColor(score) }}>
            {score > 0 ? '+' : ''}{score.toFixed(2)}
          </span>
        </div>
      )}
    </motion.div>
  );
}

/* ══ PAGE ══ */
export default function SimulationRunPage() {
  const { id } = useParams<{ id: string }>();
  const socketRef = useRef<SimulationSocket | null>(null);
  const feedRef = useRef<HTMLDivElement>(null);

  const [simStatus, setSimStatus] = useState<string>('running');
  const { events, roundNumber, totalEvents, isRunning, addEvent, updateSnapshot, setRunning, reset } =
    useSimulationLiveStore();

  useEffect(() => {
    reset();
    const token = localStorage.getItem('saibyl_access_token') || '';
    const socket = new SimulationSocket();
    socketRef.current = socket;

    socket.on('agent_action', (event) => addEvent(event as any));
    socket.on('round_start', (event) => addEvent(event as any));
    socket.on('round_end', (event) => addEvent(event as any));
    socket.on('snapshot', (event) => updateSnapshot(event as any));
    socket.on('simulation_started', () => setRunning(true));
    socket.on('simulation_completed', () => setRunning(false));
    socket.on('simulation_failed', () => setRunning(false));
    socket.on('disconnect', () => setRunning(false));

    socket.connect(id!, token);
    setRunning(true);

    return () => {
      socket.disconnect();
      socketRef.current = null;
    };
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fallback: poll API for simulation status since WebSocket may not fire terminal events
  useEffect(() => {
    if (!id) return;
    const poll = setInterval(async () => {
      try {
        const { data } = await api.get(`/simulations/${id}`);
        setSimStatus(data.status);
        if (TERMINAL_STATUSES.includes(data.status)) {
          setRunning(false);
          clearInterval(poll);
        }
      } catch { /* ignore */ }
    }, 5000);
    return () => clearInterval(poll);
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [events.length]);

  const recentEvents = events.slice(-200);

  return (
    <div className="h-screen flex flex-col bg-saibyl-void overflow-hidden">
      {/* Top bar */}
      <div className="bg-saibyl-deep border-b border-white/[0.04] px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <h1 className="text-[15px] font-bold text-saibyl-platinum">Live Simulation</h1>
          <AnimatePresence mode="wait">
            {isRunning ? (
              <motion.span
                key="running"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                className="flex items-center gap-1.5 text-[11px] font-mono px-2.5 py-1 rounded-full bg-saibyl-positive/15 text-saibyl-positive"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-saibyl-positive animate-pulse" />
                Running
              </motion.span>
            ) : (
              <motion.span
                key="stopped"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                className="flex items-center gap-1.5 text-[11px] font-mono px-2.5 py-1 rounded-full bg-saibyl-elevated text-saibyl-muted"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-saibyl-muted" />
                Stopped
              </motion.span>
            )}
          </AnimatePresence>
        </div>
        <div className="flex items-center gap-6 text-[12px] font-mono">
          <div className="flex items-center gap-2">
            <span className="text-saibyl-muted">Round</span>
            <span className="font-bold text-saibyl-indigo">{roundNumber}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-saibyl-muted">Events</span>
            <span className="font-bold text-saibyl-cyan">{totalEvents.toLocaleString()}</span>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Center — main visualization area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Agent grid / activity area */}
          <div className="flex-1 p-5 overflow-auto">
            {recentEvents.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center gap-3 text-center">
                {isRunning ? (
                  <>
                    <div className="w-12 h-12 rounded-2xl bg-saibyl-indigo/10 flex items-center justify-center">
                      <svg className="w-6 h-6 text-saibyl-indigo animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                      </svg>
                    </div>
                    <p className="text-saibyl-muted text-sm">Waiting for events...</p>
                    <p className="text-saibyl-muted/50 text-[12px] font-mono">Events will appear here in real time</p>
                  </>
                ) : (
                  <>
                    <p className="text-saibyl-muted text-sm">
                      Simulation {simStatus === 'failed' ? 'failed' : simStatus === 'stopped' ? 'stopped' : 'finished'} with no events.
                    </p>
                    <Link
                      to={`/app/simulations/${id}`}
                      className="text-saibyl-indigo text-sm hover:underline"
                    >
                      ← Back to simulation details
                    </Link>
                  </>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 auto-rows-max">
                {recentEvents
                  .filter((e) => e.event_type === 'agent_action' && e.content)
                  .slice(-30)
                  .map((evt, i) => (
                    <EventCard key={i} evt={evt} />
                  ))}
              </div>
            )}
          </div>

          {/* Sentiment timeline */}
          <div className="h-[88px] border-t border-white/[0.04] bg-saibyl-deep px-5 py-3 shrink-0">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono tracking-widest uppercase text-saibyl-muted">Sentiment Timeline</span>
              {events.length > 0 && (
                <span className="text-[10px] font-mono text-saibyl-muted">{events.filter(e => e.sentiment_score != null).length} samples</span>
              )}
            </div>
            <div className="w-full h-[52px]">
              <SentimentTimeline events={recentEvents} />
            </div>
          </div>
        </div>

        {/* Right panel — live event feed */}
        <div className="w-[300px] bg-saibyl-deep border-l border-white/[0.04] flex flex-col shrink-0">
          <div className="px-4 py-3 border-b border-white/[0.04]">
            <h2 className="text-[12px] font-semibold text-saibyl-platinum uppercase tracking-widest">Live Feed</h2>
          </div>
          <div ref={feedRef} className="flex-1 overflow-y-auto p-3 space-y-2">
            <AnimatePresence initial={false}>
              {recentEvents.length === 0 ? (
                <p className="text-[11px] text-saibyl-muted text-center mt-10 font-mono">Waiting for events...</p>
              ) : (
                recentEvents.slice(-50).map((evt, i) => (
                  <EventCard key={i} evt={evt} />
                ))
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}
