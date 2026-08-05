import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { MessageSquare, Trophy } from 'lucide-react';
import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { formatPlatforms } from '@/lib/constants';
import StatusBadge from '@/components/StatusBadge';
import type { Project, Simulation } from '@/types';

/**
 * Where testing more than one message lives.
 *
 * **It had nowhere to live before this.** N-way variant arenas, the scoreboard
 * and the paired winner test are all real and all deployed — and the only way
 * to reach any of it was to guess that a variant count inside the simulation
 * wizard was the entrance. The founder's words were "where is the Marketing
 * section?", which is the correct question to ask of a feature with no door.
 *
 * Written for someone who has not heard the term "A/B test" and will not read
 * documentation. The register is `components/founder/AudienceReview.tsx`: say
 * what the thing does in the words the person would use, and never make them
 * learn a discipline's vocabulary to operate their own product.
 *
 * Three things it deliberately does not do:
 *
 * 1. **It does not create runs of its own.** A message test *is* a simulation —
 *    same swarm, same rounds, one arena per message. A separate creation path
 *    would be a second way to configure the same object, which is how two
 *    surfaces end up disagreeing about what a run is.
 *
 * 2. **It does not let a message count be set without copy.** The count is set
 *    by `PUT /api/variants/{id}` from the messages actually written, on the
 *    run's own page. A run priced for four arenas with no copy was once billed
 *    4x and executed one, and `POST /simulations/{id}/start` refuses that
 *    outright — so this routes to the place where the two cannot disagree
 *    rather than offering a number here.
 *
 * 3. **It does not name a winner.** That is the scoreboard's job, and the
 *    scoreboard is careful about it — a paired comparison over shared agents,
 *    with the unpaired verdict shown when the two disagree. This links to it.
 */

/** A run is a message test when it was priced for more than one arena. */
function isMessageTest(sim: Simulation): boolean {
  return (sim.variants ?? 1) > 1;
}

export default function MarketingPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const projectFilter = params.get('project') ?? '';

  const [simulations, setSimulations] = useState<Simulation[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  /* Every setter fires from a promise callback rather than from the effect
     body. A synchronous `setLoading(true)` here is a cascading render that
     `react-hooks/set-state-in-effect` rejects, and the initial `true` already
     covers the first paint. */
  useEffect(() => {
    let cancelled = false;
    api
      .get('/simulations', {
        params: { limit: 100, ...(projectFilter ? { project_id: projectFilter } : {}) },
      })
      .then((r) => {
        if (cancelled) return;
        setSimulations(unwrapList<Simulation>(r.data).items);
        setError('');
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, 'Could not load your runs.'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectFilter]);

  useEffect(() => {
    api
      .get('/projects')
      .then((r) => setProjects(Array.isArray(r.data) ? r.data : r.data.items || []))
      .catch(() => {});
  }, []);

  const tests = useMemo(() => simulations.filter(isMessageTest), [simulations]);
  /* Runs that could still become a message test: the copy is only editable
     while the run has not started, so offering the others would be an invitation
     to a 409. Mirrors `_EDITABLE_STATUSES` in `api/variants.py`. */
  const editable = useMemo(
    () => simulations.filter((sim) => !isMessageTest(sim) && ['draft', 'ready'].includes(sim.status)),
    [simulations],
  );

  const projectName = projects.find((p) => p.id === projectFilter)?.name;

  return (
    <div className="p-8 bg-saibyl-void min-h-full">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-h1 text-saibyl-white mb-1">Messages</h1>
        <p className="text-small mb-2">
          {projectName
            ? `Message tests in ${projectName}.`
            : 'Test more than one version of what you want to say.'}
        </p>
        <p className="text-[13px] text-saibyl-muted max-w-2xl leading-relaxed mb-8">
          Write two or more versions of your pitch and the same room of people
          reacts to each one separately — same people, same order, so whatever
          changes is down to the words and not to who happened to be listening.
          You get a side-by-side of how each one landed, and which people changed
          their answer between them.
        </p>

        {error && (
          <div className="mb-6 px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-sm">
            {error}
          </div>
        )}

        {/* ── Tests already run or set up ── */}
        <h2 className="text-[15px] font-medium text-saibyl-platinum mb-3">
          Your message tests
        </h2>

        {loading ? (
          <div className="glass rounded-2xl p-10 text-center text-saibyl-muted text-sm">
            Loading…
          </div>
        ) : tests.length === 0 ? (
          <div className="glass rounded-2xl p-10 text-center">
            <MessageSquare className="w-6 h-6 text-saibyl-gold/50 mx-auto mb-3" />
            <p className="text-saibyl-platinum font-medium mb-2">
              You haven&rsquo;t tested more than one message yet
            </p>
            <p className="text-saibyl-muted text-[13px] max-w-lg mx-auto leading-relaxed">
              Every message you add is a full run of its own — the whole room reacts
              to it — so the price goes up with each one, and you always see the
              exact figure before anything starts. Pick a run below, or start a new
              one and add your messages on its page before you run it.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {tests.map((sim) => (
              <button
                key={sim.id}
                onClick={() =>
                  navigate(
                    sim.status === 'complete'
                      ? `/app/simulations/${sim.id}/report`
                      : `/app/simulations/${sim.id}`,
                  )
                }
                className="w-full text-left glass glass-hover rounded-xl p-5 transition-all"
              >
                <div className="flex items-center justify-between gap-3 mb-2">
                  <span className="text-[15px] font-medium text-saibyl-platinum">
                    {sim.name}
                  </span>
                  <StatusBadge status={sim.status} />
                </div>
                <p className="text-[12px] text-saibyl-muted line-clamp-1">
                  {sim.prediction_goal}
                </p>
                <div className="flex items-center gap-4 mt-2 text-[11px] text-saibyl-muted">
                  <span className="flex items-center gap-1 text-saibyl-gold">
                    <MessageSquare className="w-3 h-3" />
                    {sim.variants} messages
                  </span>
                  <span>{formatPlatforms(sim.platforms || [])}</span>
                  <span>{new Date(sim.created_at).toLocaleDateString()}</span>
                </div>
                {sim.status === 'complete' && (
                  <span className="inline-flex items-center gap-1.5 text-[12px] text-saibyl-gold mt-2.5">
                    <Trophy className="w-3.5 h-3.5" />
                    See how each one landed →
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        {/* ── Runs that can still have messages added ── */}
        <h2 className="text-[15px] font-medium text-saibyl-platinum mt-10 mb-1">
          Add messages to a run
        </h2>
        <p className="text-[12px] text-saibyl-muted mb-3 leading-relaxed max-w-2xl">
          Messages are written on the run&rsquo;s own page, and only before it starts —
          the whole point of the comparison is that the runs differed only in their
          wording, so they are fixed once one has gone.
        </p>

        {editable.length === 0 ? (
          <div className="glass rounded-2xl p-6 flex items-center justify-between gap-4">
            <p className="text-[13px] text-saibyl-muted">
              No runs are waiting to be started. Create one and you can add your
              messages before it goes.
            </p>
            <button
              onClick={() =>
                navigate(
                  `/app/simulations/new${projectFilter ? `?project=${projectFilter}` : ''}`,
                )
              }
              className="px-5 py-2 rounded-lg bg-[#C9A227] text-[#0A0F1C] font-medium text-sm transition-all hover:bg-[#D4AF37] hover:-translate-y-0.5 shrink-0"
            >
              New run →
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {editable.map((sim) => (
              <button
                key={sim.id}
                onClick={() => navigate(`/app/simulations/${sim.id}`)}
                className="w-full text-left glass glass-hover rounded-xl px-5 py-3.5 transition-all flex items-center justify-between gap-4"
              >
                <div className="min-w-0">
                  <p className="text-[14px] text-saibyl-platinum truncate">{sim.name}</p>
                  <p className="text-[11px] text-saibyl-muted truncate">
                    {formatPlatforms(sim.platforms || [])}
                  </p>
                </div>
                <span className="text-[12px] text-saibyl-gold shrink-0">
                  Write the messages →
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
