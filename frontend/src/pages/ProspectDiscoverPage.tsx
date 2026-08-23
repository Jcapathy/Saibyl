import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AxiosError } from 'axios';
import { ArrowLeft, Loader2, Search } from 'lucide-react';
import api, { unwrapList } from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import {
  DISCOVER_REQUEST_TIMEOUT_MS,
  MAX_QUERIES_PER_DISCOVERY,
  formatCredits,
} from '@/lib/gtm';
import { QueryList, RunCard } from '@/components/gtm/RunCard';
import { StageError } from '@/components/stages/StagePrimitives';
import {
  Action,
  Card,
  Ground,
  Notice,
  PageHeader,
  Rise,
  dealDelayMs,
} from '@/components/design';
import type { ICPProfile } from '@/lib/founder';
import type { DiscoveryEstimate, DiscoveryRun, Project } from '@/types';

/**
 * "Go and find me real companies who look like these buyers."
 *
 * The screen exists in the shape it does because of one endpoint:
 * `GET /gtm/estimate` returns **the actual compiled queries**, not a count of
 * them. The compiler is deterministic, so those strings are exactly what will be
 * sent to a search engine. Showing them is both the honest version of "we
 * searched the internet for you" and the only way a founder can tell, *before*
 * paying, that the audience they confirmed produces sensible searches. A query
 * that reads wrong here points at the audience field that produced it — which is
 * why each one carries what it was derived from.
 *
 * Two failure modes are rendered as their own thing rather than as errors:
 *
 * **402 means nothing was spent.** Credits are charged before the first search,
 * so a refusal happens *before* the charge — no credits, no searches, no run
 * row. Rendering that as a generic red box would leave a founder wondering what
 * they had just been billed for. The server writes the shortfall sentence with
 * the real numbers in it, and it is shown verbatim.
 *
 * **400 means the audience is too thin to search on.** Not a validation failure
 * to fix here: the remedy is on the audience, and the message says which fields.
 *
 * ---
 *
 * **What the restyle changed, and what it refused to.**
 *
 * The panel a founder is actually deciding on is the second one — how wide to
 * cast, what it costs, and the real searches underneath — so that is the screen's
 * one `stage` card and the only thing on it carrying the deep shadow. Choosing
 * the audience is an input and stays a hairline.
 *
 * The run button used to be `disabled` on a short balance, greyed to 40% with
 * the explanation in small amber text beside it. There is no such rendering any
 * more: when the balance will not cover the search there is no button at all,
 * there is the reason and the control that fixes it. Three amber boxes that each
 * said something different in the same grey body text are now `Notice`s carrying
 * the state in colour — violet where nothing can run, amber where something ran
 * and is thinner than it should be.
 */

const selectClass =
  'w-full rounded-lg bg-white border border-saibyl-border-light px-3 py-2 text-[13px] text-saibyl-ink focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

export default function ProspectDiscoverPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const projectId = params.get('project_id') ?? '';
  const profileId = params.get('icp_profile_id') ?? '';

  const [projects, setProjects] = useState<Project[]>([]);
  const [profiles, setProfiles] = useState<ICPProfile[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(false);

  const [maxQueries, setMaxQueries] = useState(MAX_QUERIES_PER_DISCOVERY);
  const [estimate, setEstimate] = useState<DiscoveryEstimate | null>(null);
  const [estimateLoading, setEstimateLoading] = useState(false);
  const [estimateError, setEstimateError] = useState('');

  const [starting, setStarting] = useState(false);
  const [refusal, setRefusal] = useState('');
  const [startError, setStartError] = useState('');
  const [run, setRun] = useState<DiscoveryRun | null>(null);

  const setParam = useCallback(
    (patch: Record<string, string>) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [key, value] of Object.entries(patch)) {
            if (value) next.set(key, value);
            else next.delete(key);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setParams],
  );

  /* --- projects ---------------------------------------------------- */
  useEffect(() => {
    let cancelled = false;
    api
      .get('/projects')
      .then((res) => {
        if (cancelled) return;
        const rows = unwrapList<Project>(res.data).items;
        setProjects(rows);
        // Preselect when there is exactly one — the founder has no decision to
        // make, and a dropdown with a single option is a step rather than a
        // choice.
        //
        // The "has one already been chosen" test runs inside the updater, off
        // `prev`, rather than off a closed-over `projectId`. That is what keeps
        // `project_id` out of this effect's dependencies — with it in, choosing
        // a product re-requested the list of products.
        if (rows.length === 1) {
          setParams(
            (prev) => {
              if (prev.get('project_id')) return prev;
              const next = new URLSearchParams(prev);
              next.set('project_id', rows[0].id);
              return next;
            },
            { replace: true },
          );
        }
      })
      .catch(() => {
        if (!cancelled) setProjects([]);
      });
    return () => {
      cancelled = true;
    };
  }, [setParams]);

  /* --- audiences on the chosen product ------------------------------ */
  useEffect(() => {
    if (!projectId) {
      setProfiles([]);
      return;
    }
    let cancelled = false;
    setProfilesLoading(true);
    api
      .get('/icp', { params: { project_id: projectId } })
      .then((res) => {
        if (cancelled) return;
        const rows = unwrapList<ICPProfile>(res.data).items;
        setProfiles(rows);
        if (rows.length === 0) return;
        // Same reasoning as above: the currently selected id is read from the
        // updater's `prev`, so picking a different audience does not re-request
        // the list it was picked from. Falls back to the newest profile when
        // the id in the URL is not one this product has.
        setParams(
          (prev) => {
            const current = prev.get('icp_profile_id');
            if (current && rows.some((p) => p.id === current)) return prev;
            const next = new URLSearchParams(prev);
            next.set('icp_profile_id', rows[0].id);
            return next;
          },
          { replace: true },
        );
      })
      .catch(() => {
        if (!cancelled) setProfiles([]);
      })
      .finally(() => {
        if (!cancelled) setProfilesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, setParams]);

  /* --- the estimate, and the real searches --------------------------- */
  useEffect(() => {
    if (!profileId) {
      setEstimate(null);
      setEstimateError('');
      return;
    }
    let cancelled = false;
    setEstimateLoading(true);
    setEstimateError('');
    // Debounced: the count control moves in single steps and each one is a
    // request that hits the query compiler.
    const timer = setTimeout(() => {
      api
        .get<DiscoveryEstimate>('/gtm/estimate', {
          params: { icp_profile_id: profileId, max_queries: maxQueries },
        })
        .then(({ data }) => {
          if (cancelled) return;
          setEstimate(data);
        })
        .catch((err) => {
          if (cancelled) return;
          setEstimate(null);
          setEstimateError(
            getErrorMessage(err, 'We could not work out what this search would cost.'),
          );
        })
        .finally(() => {
          if (!cancelled) setEstimateLoading(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [profileId, maxQueries]);

  /* --- start --------------------------------------------------------- */
  async function start() {
    setStarting(true);
    setRefusal('');
    setStartError('');
    try {
      const { data } = await api.post<DiscoveryRun>(
        '/gtm/discover',
        { icp_profile_id: profileId, max_queries: maxQueries },
        // Discovery runs inline, with a 180s server-side deadline. A client
        // timeout below that would abandon a run whose credits are already
        // spent.
        { timeout: DISCOVER_REQUEST_TIMEOUT_MS },
      );
      setRun(data);
    } catch (err) {
      if (err instanceof AxiosError && err.response?.status === 402) {
        // Refused before the charge. Kept apart from `startError` so the copy
        // underneath can promise, truthfully, that nothing was spent.
        setRefusal(getErrorMessage(err, 'You do not have enough credits for this search.'));
        return;
      }
      setStartError(getErrorMessage(err, 'The search could not be started.'));
    } finally {
      setStarting(false);
    }
  }

  const selectedProfile = profiles.find((p) => p.id === profileId) ?? null;
  const buyerCount = selectedProfile?.profile?.archetypes?.length ?? 0;
  const compiled = estimate?.queries.length ?? 0;
  /* Where a thin audience gets fixed. The product's own page when we know which
     one it is, the list of them when a deep link left us without it — either way
     a founder told "there is not enough here" has somewhere to go. */
  const audienceHref = selectedProfile
    ? `/app/projects/${selectedProfile.project_id}`
    : projectId
      ? `/app/projects/${projectId}`
      : '/app/projects';

  /* --- after the run ------------------------------------------------- */
  if (run) {
    return (
      <Ground className="min-h-full p-6 lg:p-8">
        <div className="max-w-3xl mx-auto space-y-5">
          <Rise>
            <PageHeader
              eyebrow="Company search"
              title="The search has finished"
              phrase="What came back, and the searches that brought it."
            />
          </Rise>

          <Rise delayMs={dealDelayMs(1)} className="space-y-5">
            <RunCard
              run={run}
              action={
                <div className="flex flex-wrap items-center gap-3">
                  {run.candidates_found > 0 && (
                    <Action as={Link} to={`/app/prospects?discovery_run_id=${run.id}`}>
                      See the{' '}
                      {run.candidates_found === 1
                        ? 'company'
                        : `${run.candidates_found} companies`}
                    </Action>
                  )}
                  <Action
                    kind="quiet"
                    onClick={() => {
                      setRun(null);
                      setRefusal('');
                      setStartError('');
                    }}
                  >
                    Run another search
                  </Action>
                  <Action as={Link} to="/app/prospects" kind="quiet">
                    Back to all companies
                  </Action>
                </div>
              }
            />

            {run.queries.length > 0 && (
              <Card carries="density" className="p-5" as="section">
                <h2 className="text-[13px] font-medium text-saibyl-ink mb-3">
                  What we searched for
                </h2>
                <QueryList queries={run.queries} />
              </Card>
            )}
          </Rise>
        </div>
      </Ground>
    );
  }

  /* --- the setup ------------------------------------------------------ */
  return (
    <Ground className="min-h-full p-6 lg:p-8">
      <div className="max-w-3xl mx-auto space-y-5">
        <Rise>
          <button
            type="button"
            onClick={() => navigate('/app/prospects')}
            className="inline-flex items-center gap-1.5 text-[12px] text-saibyl-muted hover:text-saibyl-ink transition-colors mb-3"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> All companies
          </button>
          <PageHeader
            eyebrow="Company search"
            title="Find companies to sell to"
            phrase="Every search, and what it costs, before a single credit moves."
          >
            <p>
              You told us who your buyers are. Now we go and search the web for
              real companies that look like them. You will see every search we
              are about to run, and what it costs, before anything happens.
            </p>
          </PageHeader>
        </Rise>

        {/* 1 — which audience. An input, so it keeps its hairline. */}
        <Card carries="density" className="p-5 space-y-4" as="section">
          <h2 className="text-[13px] font-medium text-saibyl-ink">
            Which buyers are we looking for?
          </h2>

          {projects.length > 1 && (
            <label className="block">
              <span className="block text-[12px] text-saibyl-silver mb-1.5">Product</span>
              <select
                value={projectId}
                onChange={(e) => setParam({ project_id: e.target.value, icp_profile_id: '' })}
                className={selectClass}
                style={{ colorScheme: 'light' }}
              >
                <option value="">Choose a product…</option>
                {projects.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          {projectId &&
            (profilesLoading ? (
              <div>
                <span className="block text-[12px] text-saibyl-silver mb-1.5">Your buyers</span>
                <div className="h-9 rounded-lg bg-[#14294a]/[0.04] animate-pulse" />
              </div>
            ) : profiles.length === 0 ? (
              /* Nothing can run until this is supplied, which is what violet
                 means. The way out is the button, not a sentence about it. */
              <Notice
                tone="blocked"
                title="We have not worked out who buys this one yet"
                action={
                  <Action as={Link} to={`/app/projects/${projectId}`} kind="quiet">
                    Open this product
                  </Action>
                }
              >
                We cannot search for companies that look like your buyers until we
                know who your buyers are. Open the product and do that first
                &mdash; Saibyl reads what you have uploaded and tells you who it
                thinks will buy this.
              </Notice>
            ) : (
              <label className="block">
                <span className="block text-[12px] text-saibyl-silver mb-1.5">Your buyers</span>
                <select
                  value={profileId}
                  onChange={(e) => setParam({ icp_profile_id: e.target.value })}
                  className={selectClass}
                  style={{ colorScheme: 'light' }}
                >
                  {profiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.name}
                    </option>
                  ))}
                </select>
              </label>
            ))}

          {selectedProfile && buyerCount > 0 && (
            <p className="text-[11px] text-saibyl-muted">
              {buyerCount} {buyerCount === 1 ? 'kind' : 'kinds'} of buyer in this audience.{' '}
              <Link
                to={`/app/projects/${selectedProfile.project_id}`}
                className="text-saibyl-silver hover:text-saibyl-ink underline"
              >
                Review them
              </Link>{' '}
              if a search below looks wrong.
            </p>
          )}
        </Card>

        {/* 2 — how much. The panel this screen is about: what you are buying,
               and the exact searches you are buying it for. */}
        {profileId && (
          <Card carries="stage" className="p-5 space-y-4" as="section">
            <div>
              <h2 className="text-[13px] font-medium text-saibyl-ink">
                How wide should we cast?
              </h2>
              <p className="text-[11px] text-saibyl-muted mt-1 leading-relaxed">
                More searches cover more of your audience and cost more. Fewer is cheaper and
                narrower &mdash; neither is wrong, and you can run this again.
              </p>
            </div>

            <div className="flex items-center gap-4">
              <input
                type="range"
                min={1}
                max={MAX_QUERIES_PER_DISCOVERY}
                step={1}
                value={maxQueries}
                onChange={(e) => setMaxQueries(Number(e.target.value))}
                className="flex-1 accent-[#286cf0]"
                aria-label="How many searches to run"
              />
              <span className="font-mono text-[13px] text-saibyl-ink w-24 text-right">
                up to {maxQueries}
              </span>
            </div>

            {estimateLoading && (
              <p className="flex items-center gap-2 text-[12px] text-saibyl-muted">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> Working out the searches…
              </p>
            )}

            {estimateError && !estimateLoading && (
              <Notice tone="blocked" title="We could not prepare this search">
                <span className="whitespace-pre-wrap">{estimateError}</span>
              </Notice>
            )}

            {estimate && !estimateLoading && (
              <>
                <Card carries="density" className="px-4 py-3 bg-saibyl-elevated">
                  <p className="text-[13px] text-saibyl-ink">
                    {compiled} {compiled === 1 ? 'search' : 'searches'} for{' '}
                    <span className="font-mono text-saibyl-blue">
                      {formatCredits(estimate.budget.credits_required)}
                    </span>{' '}
                    credits
                  </p>
                  {/* The server's sentence, with the real balance in it. Not
                      re-written here: it is the one place the numbers the charge
                      is actually made from are stated. */}
                  <p className="text-[11px] text-saibyl-silver mt-1 leading-relaxed">
                    {estimate.budget.message}
                  </p>
                  {estimate.budget.allowed && estimate.budget.balance_share_pct > 30 && (
                    <p className="text-[11px] text-saibyl-warning mt-1.5">
                      That is {Math.round(estimate.budget.balance_share_pct)}% of what you have
                      left.
                    </p>
                  )}
                </Card>

                {compiled > 0 && (
                  <div>
                    <h3 className="text-[12px] font-medium text-saibyl-ink mb-1">
                      Exactly what we will search for
                    </h3>
                    <p className="text-[11px] text-saibyl-muted mb-3 leading-relaxed">
                      These are the real searches, word for word. Nothing else gets sent.
                    </p>
                    <QueryList queries={estimate.queries} />
                  </div>
                )}
              </>
            )}
          </Card>
        )}

        {/* 3 — go */}
        {estimate && compiled > 0 && (
          <section className="space-y-3">
            {refusal && (
              <Notice tone="thin" title="Nothing was spent">
                {/* The server's own sentence, with the real numbers in it. */}
                <p className="whitespace-pre-wrap">{refusal}</p>
                <p className="mt-2">
                  We check your balance before the first search, so no credits left
                  your account and no searches ran. Move the slider down to run a
                  smaller search, or top up and come back.
                </p>
              </Notice>
            )}

            {startError && <StageError message={startError} />}

            {starting ? (
              <div className="flex flex-wrap items-center gap-4">
                {/* The click landed and the work is running. Announced, not
                    greyed out — a rectangle at 40% opacity with no words is
                    what this replaces. */}
                <Action as="span" aria-live="polite" className="opacity-80">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Searching&hellip;
                </Action>
                <p className="text-[11px] text-saibyl-silver leading-relaxed max-w-sm">
                  This takes a couple of minutes and runs while this page is open. Companies
                  are saved as each search finishes, so closing the tab loses the summary but
                  not the results.
                </p>
              </div>
            ) : estimate.budget.allowed ? (
              <Action onClick={start}>
                <Search className="w-4 h-4" />
                Run {compiled} {compiled === 1 ? 'search' : 'searches'} for{' '}
                {formatCredits(estimate.budget.credits_required)} credits
              </Action>
            ) : (
              /* No button, because there is nothing this button could do. The
                 reason, and the two things that change it, in its place. */
              <Notice
                tone="blocked"
                title="Not enough credits for this one"
                action={
                  <Action as={Link} to="/app/settings" kind="quiet">
                    Add credits
                  </Action>
                }
              >
                Nothing has been spent. Drag the slider above down for a smaller
                search, or top up and come back to this screen.
              </Notice>
            )}
          </section>
        )}

        {profileId && estimate && compiled === 0 && !estimateLoading && (
          <Notice
            tone="blocked"
            title="There is not enough here to search on"
            action={
              <Action as={Link} to={audienceHref} kind="quiet">
                Open the audience
              </Action>
            }
          >
            None of your buyers has enough detail to build a search from. Fill in
            what they do for a living, the tools they already use, or what they
            complain about &mdash; any one of those is enough.
          </Notice>
        )}
      </div>
    </Ground>
  );
}
