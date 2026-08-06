import { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { SimulationSocket } from '@/lib/websocket';
import { useSimulationLiveStore } from '@/store/simulation';
import type { SimulationStreamEvent, VisualizerSnapshot } from '@/store/simulation';
import { TERMINAL_STATUSES } from '@/lib/constants';
import api from '@/lib/api';

const PLATFORM_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  Twitter:   { bg: 'bg-[#C9A227]/15', text: 'text-[#C9A227]',  dot: '#C9A227' },
  Reddit:    { bg: 'bg-[#2563EB]/15', text: 'text-[#2563EB]',  dot: '#2563EB' },
  TikTok:    { bg: 'bg-[#8B5CF6]/15', text: 'text-[#8B5CF6]',  dot: '#8B5CF6' },
  Instagram: { bg: 'bg-[#8B5CF6]/15', text: 'text-[#8B5CF6]',  dot: '#8B5CF6' },
  Facebook:  { bg: 'bg-[#C9A227]/15', text: 'text-[#C9A227]',  dot: '#C9A227' },
  LinkedIn:  { bg: 'bg-[#2563EB]/15', text: 'text-[#2563EB]',  dot: '#2563EB' },
  YouTube:   { bg: 'bg-[#EF4444]/15', text: 'text-[#EF4444]',  dot: '#EF4444' },
};

/* ── Event Card ── */
function EventCard({ evt }: { evt: SimulationStreamEvent }) {
  const platform = evt.platform ?? undefined;
  const style = platform ? PLATFORM_STYLES[platform] : null;

  return (
    <motion.div
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.18 }}
      className="rounded-xl bg-white/[0.03] border border-white/[0.04] p-3 text-xs"
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-medium text-saibyl-platinum text-[12px] truncate max-w-[120px]">
          {evt.event_type}
        </span>
        {platform && style && (
          <span className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono ${style.bg} ${style.text}`}>
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: style.dot }} />
            {platform}
          </span>
        )}
      </div>
      {evt.content && (
        <p className="text-saibyl-muted text-[11px] leading-relaxed line-clamp-2">{evt.content}</p>
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

    socket.on<SimulationStreamEvent>('agent_action', addEvent);
    socket.on<SimulationStreamEvent>('round_start', addEvent);
    socket.on<SimulationStreamEvent>('round_end', addEvent);
    socket.on<VisualizerSnapshot>('snapshot', updateSnapshot);
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
          <h1 className="text-[15px] font-bold text-saibyl-platinum">Watching it happen</h1>
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
            <span className="font-bold text-saibyl-gold">{roundNumber}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-saibyl-muted">Reactions so far</span>
            <span className="font-bold text-saibyl-blue">{totalEvents.toLocaleString()}</span>
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
                    <div className="w-12 h-12 rounded-2xl bg-saibyl-gold/10 flex items-center justify-center">
                      <svg className="w-6 h-6 text-saibyl-gold animate-pulse" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                      </svg>
                    </div>
                    <p className="text-saibyl-muted text-sm">Waiting for the first reaction…</p>
                    <p className="text-saibyl-muted/50 text-[12px] font-mono">They show up here as people post</p>
                  </>
                ) : (
                  <>
                    <p className="text-saibyl-muted text-sm">
                      {simStatus === 'failed'
                        ? 'This run failed before anyone said anything.'
                        : simStatus === 'stopped'
                          ? 'You stopped this run before anyone said anything.'
                          : 'This run finished without anyone saying anything.'}
                    </p>
                    <Link
                      to={`/app/simulations/${id}`}
                      className="text-saibyl-gold text-sm hover:underline"
                    >
                      ← Back to this run
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

          {/* How the room felt is deliberately absent from this page. It is
              scored from what people wrote only after the run finishes, so
              there is nothing to plot while they are still talking. The
              measured version lives on the report. */}
        </div>

        {/* Right panel — live event feed */}
        <div className="w-[300px] bg-saibyl-deep border-l border-white/[0.04] flex flex-col shrink-0">
          <div className="px-4 py-3 border-b border-white/[0.04]">
            <h2 className="text-[12px] font-semibold text-saibyl-platinum uppercase tracking-widest">As it happens</h2>
          </div>
          <div ref={feedRef} className="flex-1 overflow-y-auto p-3 space-y-2">
            <AnimatePresence initial={false}>
              {recentEvents.length === 0 ? (
                <p className="text-[11px] text-saibyl-muted text-center mt-10 font-mono">Nothing yet…</p>
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
