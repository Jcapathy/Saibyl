import { useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { SimulationSocket } from '@/lib/websocket';
import { useSimulationLiveStore } from '@/store/simulation';

const platformColors: Record<string, string> = {
  Twitter: 'bg-blue-100 text-blue-800',
  Reddit: 'bg-orange-100 text-orange-800',
  TikTok: 'bg-pink-100 text-pink-800',
  Instagram: 'bg-purple-100 text-purple-800',
  Facebook: 'bg-indigo-100 text-indigo-800',
  LinkedIn: 'bg-cyan-100 text-cyan-800',
  YouTube: 'bg-red-100 text-red-800',
};

function sentimentColor(score: number | null): string {
  if (score === null) return 'text-saibyl-muted';
  if (score >= 0.3) return 'text-green-600';
  if (score <= -0.3) return 'text-red-600';
  return 'text-yellow-600';
}

export default function SimulationRunPage() {
  const { id } = useParams<{ id: string }>();
  const socketRef = useRef<SimulationSocket | null>(null);
  const feedRef = useRef<HTMLDivElement>(null);

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

  // Auto-scroll event feed
  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [events.length]);

  return (
    <div className="h-screen flex flex-col bg-saibyl-void">
      {/* Top bar - round counter */}
      <div className="bg-saibyl-deep border-b border-saibyl-border px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-bold text-saibyl-platinum">Live Simulation</h1>
          <span className={`text-sm px-2 py-1 rounded-full ${isRunning ? 'bg-green-100 text-green-700' : 'bg-saibyl-surface text-saibyl-muted'}`}>
            {isRunning ? 'Running' : 'Stopped'}
          </span>
        </div>
        <div className="flex items-center gap-6 text-sm">
          <div>
            <span className="text-saibyl-muted">Round:</span>{' '}
            <span className="font-bold text-saibyl-indigo">{roundNumber}</span>
          </div>
          <div>
            <span className="text-saibyl-muted">Events:</span>{' '}
            <span className="font-bold text-saibyl-indigo">{totalEvents}</span>
          </div>
        </div>
      </div>

      {/* Main content area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Center - placeholder for main visualization */}
        <div className="flex-1 flex flex-col">
          <div className="flex-1 flex items-center justify-center p-4">
            <div className="w-full h-full border-2 border-dashed border-saibyl-border rounded-lg flex items-center justify-center">
              <p className="text-saibyl-muted">Main simulation visualization area</p>
            </div>
          </div>

          {/* Bottom - sentiment timeline placeholder */}
          <div className="h-32 bg-saibyl-deep border-t border-saibyl-border px-4 py-2">
            <h3 className="text-xs font-medium text-saibyl-muted mb-1">Sentiment Timeline</h3>
            <div className="w-full h-20 border border-dashed border-saibyl-border rounded flex items-center justify-center">
              <p className="text-xs text-saibyl-muted">Sentiment chart will render here</p>
            </div>
          </div>
        </div>

        {/* Right panel - event feed */}
        <div className="w-80 bg-saibyl-deep border-l border-saibyl-border flex flex-col">
          <div className="px-4 py-3 border-b border-saibyl-border">
            <h2 className="text-sm font-semibold text-saibyl-platinum">Live Event Feed</h2>
          </div>
          <div ref={feedRef} className="flex-1 overflow-y-auto p-3 space-y-2">
            {events.length === 0 ? (
              <p className="text-xs text-saibyl-muted text-center mt-8">Waiting for events...</p>
            ) : (
              events.map((evt, i) => (
                <div key={i} className="bg-saibyl-surface rounded p-2 text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium text-saibyl-platinum">
                      {evt.agent_username || evt.event_type}
                    </span>
                    {evt.platform && (
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${platformColors[evt.platform] || 'bg-saibyl-deep'}`}>
                        {evt.platform}
                      </span>
                    )}
                  </div>
                  {evt.content && (
                    <p className="text-saibyl-muted line-clamp-2">{evt.content}</p>
                  )}
                  {evt.sentiment_score !== null && evt.sentiment_score !== undefined && (
                    <span className={`text-[10px] font-medium ${sentimentColor(evt.sentiment_score)}`}>
                      Sentiment: {evt.sentiment_score.toFixed(2)}
                    </span>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
