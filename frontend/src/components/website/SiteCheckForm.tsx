import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AxiosError } from 'axios';
import { ArrowRight } from 'lucide-react';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { Guarded } from '@/components/stages/StagePrimitives';
import PriceTag from '@/components/billing/PriceTag';
import { usePrices } from '@/lib/prices';
import type { SiteCheck } from './types';

/**
 * The way in for a founder who has already built something.
 *
 * One box, one address. The backend fetches the page, renders it the way a
 * buyer's browser would, and judges what it finds; this form's only job is to
 * hand the address over and say plainly what went wrong if it could not.
 *
 * The API is the only authority on money and on what counts as a bad address.
 * A credit shortfall arrives as a 402 with the sentence to show, and this form
 * shows that sentence with the one control that fixes it — the same contract
 * the clearance form follows. A malformed address arrives as a 400/422 with
 * plain language in `detail`, rendered as given.
 *
 * The second box is optional, and on 2026-08-28 it stopped being *invited*.
 *
 * It read "A site you admire (optional)" over "We'll measure yours against
 * theirs — type, color, spacing, the exact numbers", and the founder who found
 * this had duly filled it in — with his own url. The comparison half of the
 * check then measured saibyl.com against saibyl.com and told him nothing.
 *
 * His objection was not about that mistake. It was that the workflow asks the
 * wrong question: **a founder wants their own page made better, not a ranking
 * against somebody else's.** Optional is not enough when the copy reads as a
 * step. So the label no longer flatters the idea, and the help text says
 * plainly that the page is graded on its own merits either way.
 *
 * The field survives because "make it feel more like Linear" is real direction
 * — but it is direction for the rewrite, never the yardstick for the score.
 * Left empty it sends nothing, so the backend never sees an empty-string
 * address.
 */

const inputBase =
  'w-full rounded-xl bg-white border border-saibyl-border-light px-3 py-2.5 text-[13.5px] text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

export default function SiteCheckForm({
  productId,
  onStarted,
}: {
  productId: string;
  /** The freshly queued check. The caller polls it the rest of the way. */
  onStarted: (check: SiteCheck) => void;
}) {
  const prices = usePrices();
  const [address, setAddress] = useState('');
  const [reference, setReference] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; billing: boolean } | null>(
    null,
  );

  async function submit() {
    // Stated rather than enforced by a greyed-out control: an empty box gets
    // the sentence that unblocks it, not a button that ignores the click.
    const trimmed = address.trim();
    if (!trimmed) {
      setError({
        message:
          'Paste the address first — “yoursite.com” is enough, with or without the https part.',
        billing: false,
      });
      return;
    }
    setSubmitting(true);
    setError(null);

    // A founder types "yoursite.com"; the fetcher needs a scheme. Added
    // quietly here rather than bounced back as a correction — and the site
    // they admire gets exactly the same courtesy.
    const withScheme = (value: string) =>
      /^https?:\/\//i.test(value) ? value : `https://${value}`;
    const url = withScheme(trimmed);

    const body: { project_id: string; url: string; reference_url?: string } = {
      project_id: productId,
      url,
    };
    const admired = reference.trim();
    if (admired) body.reference_url = withScheme(admired);

    try {
      const { data } = await api.post<SiteCheck>('/website/check', body);
      onStarted(data);
    } catch (err) {
      const status = err instanceof AxiosError ? err.response?.status : undefined;
      setError({
        message: getErrorMessage(err, 'We could not start reading your site.'),
        // 402 is a credit shortfall. The API's own sentence says what is
        // short; this adds the one control that fixes it.
        billing: status === 402,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rounded-xl border border-saibyl-border bg-white p-5 space-y-4">
      <div>
        <label
          htmlFor="site-check-url"
          className="block text-[14px] font-medium text-saibyl-ink"
        >
          Have a site already? Paste the address &mdash; we&rsquo;ll read it
          like a buyer would.
        </label>
        <p className="text-[12px] text-saibyl-muted mt-1 leading-relaxed">
          We load the page the way a buyer&rsquo;s browser would and judge what
          a stranger sees: what it says, whether it earns trust, how it reads
          on a phone, and where the route to acting breaks down.
        </p>
      </div>

      <input
        id="site-check-url"
        type="text"
        inputMode="url"
        autoComplete="url"
        value={address}
        onChange={(e) => setAddress(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            void submit();
          }
        }}
        placeholder="yoursite.com"
        className={inputBase}
      />

      {/* The second field used to read "A site you admire (optional)" over
          "We'll measure yours against theirs — type, color, spacing, the exact
          numbers", and that framing was the defect.

          A founder does not want to be told how somebody else's page is better
          than theirs; they want their own page made better. Marking the field
          optional was never enough, because the copy invited it as a step — the
          founder who found this had filled it in with his OWN url, and the
          comparison half of the check then told him nothing.

          It stays, because "make it feel more like Linear" is real direction.
          But it is direction for the rewrite, not the yardstick for the score:
          the check is graded against a standard, not against a competitor. */}
      <div>
        <label
          htmlFor="site-check-reference"
          className="block text-[12.5px] text-saibyl-silver"
        >
          A site whose feel you want{' '}
          <span className="text-saibyl-muted">(optional, rarely needed)</span>
        </label>
        <p className="text-[11.5px] text-saibyl-muted mt-0.5 mb-1.5 leading-relaxed">
          Your page is graded on its own merits either way. Name one only if you
          want the rewrite to lean somewhere specific.
        </p>
        <input
          id="site-check-reference"
          type="text"
          inputMode="url"
          autoComplete="url"
          value={reference}
          onChange={(e) => setReference(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              void submit();
            }
          }}
          placeholder="theirsite.com"
          className={inputBase}
        />
      </div>

      {error && (
        <div className="rounded-xl border border-saibyl-negative/25 bg-saibyl-negative/[0.07] p-4">
          <p className="text-[13px] text-saibyl-negative leading-relaxed">
            {error.message}
          </p>
          {error.billing && (
            <Link
              to="/app/settings/billing"
              className="inline-flex items-center gap-1.5 mt-3 px-3.5 py-1.5 rounded-lg bg-saibyl-blue text-saibyl-paper text-[12px] font-semibold hover:bg-saibyl-blue-hover transition-colors"
            >
              Add credits
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          )}
        </div>
      )}

      <div>
        {/* Priced before the work, not refused after it. */}
        <div className="mb-3">
          <PriceTag entry={prices?.website_check} />
        </div>
        <Guarded
          label="Check my site"
          onClick={submit}
          busy={submitting}
          busyLabel="Reading your site…"
        />
        <p className="text-[11px] text-saibyl-muted mt-3 leading-relaxed">
          The page&rsquo;s own words become part of your material, so the
          audience step reads them alongside anything you upload.
        </p>
      </div>
    </div>
  );
}
