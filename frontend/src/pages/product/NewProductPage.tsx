import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { StageError } from '@/components/stages/StagePrimitives';
import { Action, Card, Ground, PageHeader, Rise } from '@/components/design';

/**
 * Add a product.
 *
 * Two fields, and only the name is required. This is the second screen a new
 * founder sees and everything it asks for is a reason not to continue — the
 * description exists because it is the only thing an agent can read if nothing
 * is ever uploaded, and it says so rather than presenting itself as metadata.
 *
 * ---
 *
 * **The restyle (2026-08-23).** It painted `bg-saibyl-void` over the radial
 * wash `<body>` carries and wrote its heading in `saibyl-white` — legacy
 * dark-theme names that still resolve to light values, which is exactly why
 * nobody noticed the second screen of the product had never been converted. It
 * now composes `components/design/`, and its button row is the artboard's own:
 * the gradient for the thing to press, a white button on a hairline beside it.
 */
export default function NewProductPage() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const inputBase =
    'w-full rounded-xl bg-white border border-saibyl-border-light px-3 py-2.5 text-[13.5px] text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20';

  async function create() {
    const trimmed = name.trim();
    if (!trimmed) {
      // Stated rather than enforced by a greyed-out button. The founder gets a
      // sentence telling them what is wrong instead of a control that does
      // nothing when clicked.
      setError('Give it a name first — whatever you call it in conversation is fine.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const { data } = await api.post<{ id: string }>('/projects', {
        name: trimmed,
        description: description.trim() || null,
      });
      navigate(`/app/products/${data.id}/audience`);
    } catch (err) {
      setError(getErrorMessage(err, 'We could not create that.'));
      setSaving(false);
    }
  }

  return (
    <Ground className="p-6 lg:p-8 min-h-full">
      <div className="max-w-xl mx-auto">
        <Link
          to="/app/home"
          className="inline-flex items-center gap-1.5 text-[12px] text-saibyl-muted hover:text-saibyl-ink transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Your products
        </Link>

        <Rise className="mt-3">
          <PageHeader
            eyebrow="Your workspace"
            title="New product"
            phrase="A name is enough to start. The rest arrives as you go."
          >
            <p>
              A product is whatever you are trying to sell. Next you will upload
              the deck or the landing page, and we will work out who buys it.
            </p>
          </PageHeader>

          {/* The one panel this screen is about. */}
          <Card carries="stage" className="p-6 mt-6 space-y-5">
            <div>
              <label
                htmlFor="product-name"
                className="block text-[12.5px] text-saibyl-silver mb-1.5"
              >
                What is it called?
              </label>
              <input
                id="product-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. ParryAI"
                className={inputBase}
              />
            </div>

            <div>
              <label
                htmlFor="product-description"
                className="block text-[12.5px] text-saibyl-silver mb-1.5"
              >
                What does it do, in one line?
              </label>
              <textarea
                id="product-description"
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g. Catches bad pull requests before a human reviews them"
                className={`${inputBase} resize-y`}
              />
              <p className="text-[11px] text-saibyl-muted/70 mt-1.5 leading-relaxed">
                Optional. If you never upload anything, this one line is the only
                thing the simulated buyers get to read — so it is worth a minute.
                And nothing written yet is fine — the next step takes a deck or a
                landing page, or just your answers to five short questions.
              </p>
            </div>

            {error && <StageError message={error} />}

            {/* The artboard's row: the gradient for the thing to press, and a
                white button on a hairline beside it. There is no third
                rendering — no greyed-out "Create it" while the name is empty,
                because `create()` says what is wrong instead. */}
            <div className="flex flex-wrap items-center gap-2.5">
              {saving ? (
                /* Announced, not disabled. The click landed and the work is
                   running; a grey rectangle with no words is what this
                   replaces. */
                <Action as="span" aria-live="polite" className="opacity-70 pointer-events-none">
                  Creating…
                </Action>
              ) : (
                <Action onClick={create}>Create it</Action>
              )}
              <Action as={Link} to="/app/home" kind="quiet">
                Not now
              </Action>
            </div>
          </Card>
        </Rise>
      </div>
    </Ground>
  );
}
