import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { isFinished } from '@/lib/status';
import {
  Action,
  Card,
  Deal,
  Eyebrow,
  Ground,
  Notice,
  PageHeader,
  Rise,
} from '@/components/design';
import type { Simulation } from '@/types';

/** `POST /comparison` — a per-run rollup, not a `simulations` row. */
interface SimSummary {
  simulation_id: string;
  name: string;
  persona_packs: string[];
  platforms: string[];
  agent_count: number;
  max_rounds: number;
  total_events: number;
  // Null when the run has no measured sentiment. It used to be computed from
  // the dead `metadata.sentiment` key and defaulted to 0.0, so two unmeasured
  // runs compared as identically neutral — a fabricated agreement.
  avg_sentiment: number | null;
  sentiment_agents?: number | null;
  top_platform: string;
  event_breakdown: Record<string, number>;
  platform_breakdown: Record<string, number>;
}

/**
 * Two rooms, side by side.
 *
 * ---
 *
 * **Restyled onto the shared design system on 2026-08-23.** It had never been
 * converted, and the reason nobody noticed is the same one that hid
 * `ProductHomePage`: every colour on it was a legacy dark-theme alias —
 * `saibyl-white`, `saibyl-platinum`, `saibyl-gold`, `saibyl-void` — and those
 * names still resolve, because the token file remapped them to light values
 * when the theme flipped. The page rendered, so it looked converted.
 *
 * Four things changed and none of them is spacing:
 *
 * 1. `Ground` under the page. `AppLayout` paints a flat `bg-saibyl-paper`
 *    over the wash `<body>` carries, so a page that wants canvas rule 1 has to
 *    re-lay it.
 * 2. `.glass rounded-2xl` panels with no depth class became `Card carries=…`,
 *    so the picker and the table claim to be the subject and the written
 *    comparison beside them does not.
 * 3. Every state the page reported in grey body text — no finished runs, a
 *    failed comparison — is a tinted `Notice` with the control that resolves
 *    it. That is the whole of canvas rule "colour carries state".
 * 4. `disabled` is gone from the compare button. The founder's standing rule:
 *    a control either runs, or it is blocked with the reason beside it. The
 *    reason ("Pick at least two.") was already sitting next to a grey
 *    rectangle; now the button is real and the sentence does the work.
 *
 * Density is unchanged: 13px table, 12px captions, the same row rhythm. Only
 * `PageHeader` is larger, and it owns those sizes.
 */
export default function ComparisonPage() {
  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<{ simulations: SimSummary[]; analysis: string } | null>(null);

  useEffect(() => {
    api.get('/simulations', { params: { limit: 50 } }).then((r) => {
      // `isFinished` rather than a hand-written list. The database holds both
      // `complete` and `completed`, and a list built from one spelling silently
      // hides half the runs a founder is trying to compare.
      const finished = unwrapList<Simulation>(r.data).items.filter((s: Simulation) =>
        isFinished(s.status),
      );
      setSimulations(finished);
    }).catch((err) => {
      setError(getErrorMessage(err, 'We could not load your runs.'));
    });
  }, []);

  const toggleSim = (id: string) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : prev.length < 5 ? [...prev, id] : prev
    );
  };

  const runComparison = async () => {
    if (selected.length < 2) return;
    setLoading(true);
    setError('');
    try {
      const { data } = await api.post('/compare', { simulation_ids: selected });
      setResult(data);
    } catch (err) {
      // Previously swallowed, which left the button flipping back to its idle
      // label having said nothing about why no table appeared.
      setError(getErrorMessage(err, 'We could not compare those runs.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Ground className="p-6 lg:p-8 min-h-full">
      <div className="max-w-5xl mx-auto">
        <Rise className="mb-7">
          <PageHeader
            eyebrow="Your runs"
            title="Put your runs side by side"
            phrase="Two rooms, the same product, and the difference between them."
          >
            <p>
              Pick two to five finished runs and we will show you what changed
              between them &mdash; how people took it, how much they had to say,
              and where they said it. Nothing on the table is averaged across
              runs: each column is one room, read on its own, so a row that
              cannot be measured says so instead of settling at zero.
            </p>
          </PageHeader>
        </Rise>

        {!result ? (
          /* `stage` — the one panel this screen is about while nothing has been
             compared yet. When the table arrives it takes the role over, and
             this branch is gone, so there is still exactly one per screen. */
          <Card carries="stage" className="p-6 mb-6">
            <Eyebrow className="mb-4">Pick the runs</Eyebrow>

            {simulations.length === 0 ? (
              /* Was two lines of grey text and a link that looked like prose.
                 A comparison with nothing to compare is a blocked state, and
                 the rule for a blocked state is the reason plus the button
                 that unblocks it. */
              <Notice
                tone="blocked"
                title="You have no finished runs yet"
                action={
                  <Action as={Link} to="/app/simulations/new" kind="quiet">
                    Start a run
                  </Action>
                }
              >
                A comparison needs at least two rooms that have finished
                arguing. Start one and it appears here the moment it lands.
              </Notice>
            ) : (
              <div className="space-y-2">
                {simulations.map((sim, i) => {
                  const isSelected = selected.includes(sim.id);
                  return (
                    /* Dealt at the artboard's 70ms, capped inside
                       `dealDelayMs` so fifty finished runs do not become a
                       four-second wait for the tail. */
                    <Deal key={sim.id} index={i}>
                      <button
                        type="button"
                        onClick={() => toggleSim(sim.id)}
                        aria-pressed={isSelected}
                        className="w-full text-left rounded-xl"
                      >
                        {/* `density`. A row in a list of fifty gets a hairline
                            and nothing else — shadow every row and the panel
                            turns to soup. */}
                        <Card
                          carries="density"
                          className={`p-3 rounded-xl transition-colors ${
                            isSelected
                              ? 'border-saibyl-blue/50 bg-saibyl-blue/[0.06]'
                              : 'hover:border-saibyl-border-light'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <span className="text-[14px] font-medium text-saibyl-ink">
                                {sim.name}
                              </span>
                              <span className="text-[11px] text-saibyl-muted ml-3">
                                {sim.agent_count ?? '—'} people
                              </span>
                              <span className="text-[11px] text-saibyl-muted ml-2">
                                {new Date(sim.created_at).toLocaleDateString()}
                              </span>
                            </div>
                            {isSelected && (
                              /* `.bg-saibyl-blue` carries the system gradient
                                 from `index.css`, so the tick is the same blue
                                 the primary action is, not a flat fill. */
                              <div className="w-5 h-5 rounded-full bg-saibyl-blue flex items-center justify-center shrink-0">
                                <svg
                                  className="w-3 h-3 text-white"
                                  fill="none"
                                  viewBox="0 0 24 24"
                                  stroke="currentColor"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={3}
                                    d="M5 13l4 4L19 7"
                                  />
                                </svg>
                              </div>
                            )}
                          </div>
                        </Card>
                      </button>
                    </Deal>
                  );
                })}
              </div>
            )}

            <div className="flex items-center justify-between mt-4 gap-4">
              {/* The reason, beside the control. This sentence is why the
                  button no longer needs a `disabled` attribute: it says what
                  is missing, and `runComparison` refuses a set of one on its
                  own rather than relying on a greyed rectangle to. */}
              <p className="text-[12px] text-saibyl-muted">
                {selected.length === 0
                  ? 'Pick at least two.'
                  : selected.length === 1
                    ? 'Pick one more — you need at least two to compare.'
                    : `${selected.length} picked. You can compare up to five at once.`}
              </p>
              {loading ? (
                /* While it is running there is no button at all, which is how
                   a second POST is prevented without a grey rectangle. */
                <span className="shrink-0 text-[12.5px] font-extrabold text-saibyl-blue">
                  Comparing…
                </span>
              ) : (
                <Action onClick={runComparison} className="shrink-0">
                  Compare them
                </Action>
              )}
            </div>

            {error && (
              <Notice tone="blocked" title="We could not compare those runs" className="mt-4">
                {error}
              </Notice>
            )}
          </Card>
        ) : (
          <>
            {/* Results — the table is now the subject of the screen. */}
            <Deal index={0}>
              <Card carries="stage" className="p-6 mb-6">
                <Eyebrow className="mb-4">Side by side</Eyebrow>
                <div className="overflow-x-auto">
                  <table className="w-full text-[13px]">
                    <thead>
                      <tr className="border-b border-saibyl-border">
                        <th className="text-left py-3 pr-4 text-saibyl-muted font-medium">&nbsp;</th>
                        {result.simulations.map((s) => (
                          <th key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-ink font-medium">{s.name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-saibyl-border">
                      <tr>
                        <td className="py-3 pr-4 text-saibyl-muted">Posts and replies</td>
                        {result.simulations.map((s) => (
                          <td key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-ink font-mono tabular-nums">{s.total_events}</td>
                        ))}
                      </tr>
                      <tr>
                        <td className="py-3 pr-4 text-saibyl-muted">
                          How they felt
                          <span className="block text-[11px] text-saibyl-muted/70">
                            +1 loved it, &minus;1 hated it
                          </span>
                        </td>
                        {result.simulations.map((s) => (
                          <td key={s.simulation_id} className={`text-center py-3 px-3 font-mono tabular-nums ${s.avg_sentiment === null ? 'text-saibyl-muted' : s.avg_sentiment > 0.2 ? 'text-saibyl-positive' : s.avg_sentiment < -0.2 ? 'text-saibyl-negative' : 'text-saibyl-muted'}`}>
                            {s.avg_sentiment === null ? <span title="Nothing in this run could be measured, so it cannot be compared on this row.">not measured</span> : s.avg_sentiment.toFixed(3)}
                          </td>
                        ))}
                      </tr>
                      <tr>
                        <td className="py-3 pr-4 text-saibyl-muted">People in the room</td>
                        {result.simulations.map((s) => (
                          <td key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-ink font-mono tabular-nums">{s.agent_count}</td>
                        ))}
                      </tr>
                      <tr>
                        <td className="py-3 pr-4 text-saibyl-muted">Busiest platform</td>
                        {result.simulations.map((s) => (
                          /* Ink, not blue. Blue is spent on things you press;
                             a measured value wearing it reads as a link that
                             does nothing. */
                          <td key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-ink">{s.top_platform}</td>
                        ))}
                      </tr>
                      <tr>
                        <td className="py-3 pr-4 text-saibyl-muted">Groups of buyers</td>
                        {result.simulations.map((s) => (
                          <td key={s.simulation_id} className="text-center py-3 px-3 text-saibyl-muted text-[11px]">{s.persona_packs.join(', ') || 'Worked out fresh'}</td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              </Card>
            </Deal>

            {/* The written comparison — a claim to weigh, not the subject. */}
            <Deal index={1}>
              <Card carries="meaning" className="p-6 mb-6">
                <Eyebrow className="mb-4">What changed between them</Eyebrow>
                <p className="text-[13px] text-saibyl-silver leading-relaxed whitespace-pre-wrap">{result.analysis}</p>
              </Card>
            </Deal>

            <Action
              kind="quiet"
              onClick={() => { setResult(null); setError(''); }}
            >
              ← Compare a different set
            </Action>
          </>
        )}
      </div>
    </Ground>
  );
}
