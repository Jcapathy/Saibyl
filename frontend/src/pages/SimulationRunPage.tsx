import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { SimulationSocket } from '@/lib/websocket';
import { useSimulationLiveStore } from '@/store/simulation';
import type { SimulationStreamEvent, VisualizerSnapshot } from '@/store/simulation';
import { TERMINAL_STATUSES } from '@/lib/constants';
import api from '@/lib/api';
import { EmptyState } from '@/components/stages/StagePrimitives';
import { Card, Deal, Eyebrow, Ground, Notice, PageHeader, Rise } from '@/components/design';

/**
 * The one genuinely live surface in the app.
 *
 * It was also the one page still painting `bg-saibyl-void` — a flat `#f8fbff`
 * laid over the radial wash `<body>` carries — with its own `saibyl-platinum`
 * and `saibyl-gold` legacy aliases on top. Those names resolve to light values,
 * which is exactly why nobody noticed the page had never been converted.
 *
 * Two things are true of this screen and of no other, and both are said with
 * the design system's own vocabulary rather than hand-rolled here:
 *
 *   - the eyebrow's dot pulses (`PageHeader live`) while the run is open. It is
 *     a state, not decoration, and it stops meaning anything the moment a
 *     static surface wears it;
 *   - a run in progress with nothing to show yet is a cyan `Notice tone="live"`,
 *     not grey body text.
 *
 * The polling and the socket wiring below are untouched.
 */

const PLATFORM_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  Twitter:   { bg: 'bg-[#286cf0]/10', text: 'text-[#1e5ad9]',  dot: '#286cf0' },
  Reddit:    { bg: 'bg-[#286cf0]/10', text: 'text-[#1e5ad9]',  dot: '#286cf0' },
  TikTok:    { bg: 'bg-[#8b73ee]/10', text: 'text-[#6a4fe0]',  dot: '#8b73ee' },
  Instagram: { bg: 'bg-[#8b73ee]/10', text: 'text-[#6a4fe0]',  dot: '#8b73ee' },
  Facebook:  { bg: 'bg-[#286cf0]/10', text: 'text-[#1e5ad9]',  dot: '#286cf0' },
  LinkedIn:  { bg: 'bg-[#286cf0]/10', text: 'text-[#1e5ad9]',  dot: '#286cf0' },
  YouTube:   { bg: 'bg-[#ff6e79]/15', text: 'text-[#d92d3c]',  dot: '#ff6e79' },
};

/* ── Event Card ── */
/**
 * One reaction. `carries="density"` — a hairline, no shadow: these arrive by
 * the hundred and shadowing every one of them turns the page to soup.
 *
 * `Deal` at index 0 rather than a framer-motion `initial`/`animate` pair. The
 * cards stream in one at a time, so there is no sequence to stagger — what is
 * wanted is the system's own 450ms slide on each arrival, and unlike the
 * framer version it collapses to nothing under `prefers-reduced-motion`.
 */
function EventCard({ evt }: { evt: SimulationStreamEvent }) {
  const platform = evt.platform ?? undefined;
  const style = platform ? PLATFORM_STYLES[platform] : null;

  return (
    <Deal index={0}>
      <Card carries="density" className="p-3 text-xs">
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-medium text-saibyl-ink text-[12px] truncate max-w-[120px]">
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
      </Card>
    </Deal>
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

  /* Why nobody spoke, in the words of whichever ending actually happened. A
     stopped run and a failed one are not the same news. */
  const silentBody =
    simStatus === 'failed'
      ? 'This run failed before anyone said anything.'
      : simStatus === 'stopped'
        ? 'You stopped this run before anyone said anything.'
        : 'This run finished without anyone saying anything.';

  return (
    <Ground className="h-screen flex flex-col overflow-hidden">
      <Rise className="shrink-0 px-6 lg:px-8 pt-6 pb-5 border-b border-saibyl-border">
        <PageHeader
          /* The one place in the app that earns the pulsing dot. The run is
             genuinely open, and the eyebrow says so for as long as it is. */
          eyebrow={isRunning ? 'Running now' : 'Not running'}
          live={isRunning}
          title="Watching it happen"
          mark={
            <>
              Round{' '}
              <span className="font-mono font-bold text-saibyl-ink">{roundNumber}</span>
              {' · '}
              <span className="font-mono font-bold text-saibyl-blue">
                {totalEvents.toLocaleString()}
              </span>{' '}
              reactions so far
            </>
          }
          phrase="The room is talking. This is it, as it lands."
        >
          {/* Two lines, deliberately. This page is mostly feed, and a header
              that teaches for five lines is a header that pushes the thing it
              is describing off the screen. */}
          <p>
            Each card is one person reacting, in the order they posted. Close
            this page whenever you like &mdash; the run keeps going, and the
            write-up waits on the run&rsquo;s own page.
          </p>
        </PageHeader>
      </Rise>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* Center — main visualization area */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Agent grid / activity area */}
          <div className="flex-1 p-5 overflow-auto">
            {recentEvents.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center">
                {isRunning ? (
                  /* Cyan, because something is happening. This was grey body
                     text under a pulsing lightning bolt, which read as an
                     error state on a run that was working perfectly. */
                  <Notice
                    tone="live"
                    title="Waiting for the first reaction"
                    className="max-w-md"
                  >
                    The room is being spoken to now. Reactions appear here the
                    moment somebody posts one, and the feed on the right keeps
                    the running order.
                  </Notice>
                ) : (
                  <EmptyState
                    headline="Nobody said anything"
                    body={silentBody}
                    action={{
                      label: 'Back to this run',
                      href: `/app/simulations/${id}`,
                    }}
                  />
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

        {/* Right panel — live event feed. Glass over the wash, as the rail is
            glass on the artboard, rather than the opaque panel that used to
            cover the ground here. */}
        <div className="w-[300px] bg-white/[0.72] backdrop-blur-[18px] border-l border-saibyl-border flex flex-col shrink-0">
          <div className="px-4 py-3 border-b border-saibyl-border">
            <Eyebrow>As it happens</Eyebrow>
          </div>
          <div ref={feedRef} className="flex-1 overflow-y-auto p-3 space-y-2">
            {recentEvents.length === 0 ? (
              <p className="text-[11px] text-saibyl-muted text-center mt-10 font-mono">Nothing yet…</p>
            ) : (
              recentEvents.slice(-50).map((evt, i) => (
                <EventCard key={i} evt={evt} />
              ))
            )}
          </div>
        </div>
      </div>
    </Ground>
  );
}
