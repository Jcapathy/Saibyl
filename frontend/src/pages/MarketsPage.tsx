import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '@/lib/api';
import StatusBadge from '@/components/StatusBadge';

interface Market {
  id: string;
  platform: string;
  title: string;
  status: string;
  outcomes: { label: string; current_probability: number }[];
  volume_usd: number;
  closes_at: string;
  external_url: string;
  created_at: string;
}

export default function MarketsPage() {
  const [markets, setMarkets] = useState<Market[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchPlatform, setSearchPlatform] = useState<'polymarket' | 'kalshi'>('polymarket');
  const [searchResults, setSearchResults] = useState<Record<string, unknown>[]>([]);
  const [importUrl, setImportUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [importing, setImporting] = useState(false);
  const [tab, setTab] = useState<'imported' | 'search'>('imported');

  useEffect(() => {
    api.get('/markets').then((r) => { setMarkets(r.data); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  const [error, setError] = useState('');

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setError('');
    try {
      const r = await api.get('/markets/search', { params: { query: searchQuery, platform: searchPlatform, limit: 12 } });
      setSearchResults(r.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Search failed');
    }
    setSearching(false);
  };

  const handleImport = async () => {
    if (!importUrl.trim()) return;
    setImporting(true);
    setError('');
    try {
      await api.post('/markets/import', { url: importUrl });
      setImportUrl('');
      const r = await api.get('/markets');
      setMarkets(r.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Import failed');
    }
    setImporting(false);
  };

  const yesProb = (m: Market) => {
    const yes = m.outcomes?.find((o) => o.label?.toLowerCase() === 'yes');
    return yes ? Math.round(yes.current_probability * 100) : null;
  };

  return (
    <div className="p-8 bg-saibyl-void min-h-full">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-h1 text-saibyl-white">Prediction Markets</h1>
            <p className="text-small mt-1">Import markets from Kalshi and Polymarket. Run AI-powered predictions.</p>
          </div>
        </div>

        {error && (
          <div className="mb-4 px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-sm">
            {error}
            <button onClick={() => setError('')} className="ml-3 underline">dismiss</button>
          </div>
        )}

        {/* Import bar */}
        <div className="glass rounded-2xl p-5 mb-6">
          <div className="flex gap-3">
            <input
              type="url"
              value={importUrl}
              onChange={(e) => setImportUrl(e.target.value)}
              placeholder="Paste a Kalshi or Polymarket market URL..."
              className="flex-1 bg-saibyl-surface border border-saibyl-border rounded-lg px-4 py-2.5 text-sm text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:border-saibyl-border-active"
            />
            <button
              onClick={handleImport}
              disabled={importing || !importUrl.trim()}
              className="bg-saibyl-indigo text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-[#4B4FDE] transition-colors disabled:opacity-40"
            >
              {importing ? 'Importing...' : 'Import'}
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-6 p-1 glass rounded-xl w-fit">
          {(['imported', 'search'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-5 py-2 rounded-lg text-sm font-medium transition-all ${
                tab === t ? 'bg-saibyl-indigo text-white' : 'text-saibyl-muted hover:text-saibyl-platinum'
              }`}
            >
              {t === 'imported' ? `My Markets (${markets.length})` : 'Search Markets'}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {tab === 'imported' ? (
          loading ? (
            <div className="text-center py-20 text-saibyl-muted">Loading...</div>
          ) : markets.length === 0 ? (
            <div className="glass rounded-2xl p-16 text-center">
              <div className="text-4xl mb-4">📈</div>
              <h3 className="text-h2 text-saibyl-white mb-2">No markets imported yet</h3>
              <p className="text-small max-w-sm mx-auto">Paste a Kalshi or Polymarket URL above, or search for markets to import.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {markets.map((m) => {
                const prob = yesProb(m);
                return (
                  <Link
                    key={m.id}
                    to={`/app/markets/${m.id}`}
                    className="block glass glass-hover rounded-xl p-5 transition-all duration-200"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className="font-mono text-[10px] tracking-[0.15em] uppercase text-saibyl-cyan">{m.platform}</span>
                          <StatusBadge status={m.status} />
                        </div>
                        <h3 className="text-[15px] font-medium text-saibyl-white truncate">{m.title}</h3>
                        <p className="text-[12px] text-saibyl-muted mt-1">
                          Vol: ${(m.volume_usd || 0).toLocaleString()}
                          {m.closes_at && ` · Closes ${new Date(m.closes_at).toLocaleDateString()}`}
                        </p>
                      </div>
                      {prob !== null && (
                        <div className="text-right shrink-0">
                          <div className="text-2xl font-display font-bold text-gradient">{prob}%</div>
                          <div className="text-[11px] text-saibyl-muted">YES</div>
                        </div>
                      )}
                    </div>
                  </Link>
                );
              })}
            </div>
          )
        ) : (
          <div>
            {/* Search controls */}
            <div className="flex gap-3 mb-6">
              <div className="flex gap-1 p-1 glass rounded-lg">
                {(['polymarket', 'kalshi'] as const).map((p) => (
                  <button
                    key={p}
                    onClick={() => setSearchPlatform(p)}
                    className={`px-4 py-1.5 rounded-md text-xs font-medium transition-all capitalize ${
                      searchPlatform === p ? 'bg-saibyl-elevated text-saibyl-platinum' : 'text-saibyl-muted'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="Search prediction markets..."
                className="flex-1 bg-saibyl-surface border border-saibyl-border rounded-lg px-4 py-2 text-sm text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:border-saibyl-border-active"
              />
              <button
                onClick={handleSearch}
                disabled={searching}
                className="bg-saibyl-indigo text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-[#4B4FDE] disabled:opacity-40"
              >
                {searching ? 'Searching...' : 'Search'}
              </button>
            </div>

            {searchResults.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {searchResults.map((r, i) => (
                  <div key={i} className="glass rounded-xl p-5">
                    <h4 className="text-[14px] font-medium text-saibyl-platinum mb-2 line-clamp-2">{String(r.title || '')}</h4>
                    <div className="flex items-center justify-between mt-3">
                      <span className="text-[12px] text-saibyl-muted">
                        Vol: ${Number(r.volume_usd || 0).toLocaleString()}
                      </span>
                      <button
                        onClick={() => { setImportUrl(String(r.url || '')); setTab('imported'); handleImport(); }}
                        className="text-[12px] text-saibyl-indigo hover:text-saibyl-cyan transition-colors font-medium"
                      >
                        Import →
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-16 text-saibyl-muted text-sm">
                Search for prediction markets on {searchPlatform}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
