import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import { Guarded, StageError } from '@/components/stages/StagePrimitives';

/**
 * Add a product.
 *
 * Two fields, and only the name is required. This is the second screen a new
 * founder sees and everything it asks for is a reason not to continue — the
 * description exists because it is the only thing an agent can read if nothing
 * is ever uploaded, and it says so rather than presenting itself as metadata.
 */
export default function NewProductPage() {
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const inputBase =
    'w-full rounded-lg bg-[#0B1120] border border-white/[0.08] px-3 py-2.5 text-[13.5px] text-saibyl-platinum placeholder-saibyl-muted/40 focus:outline-none focus:ring-1 focus:ring-saibyl-gold/50';

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
    <div className="p-6 lg:p-8 bg-saibyl-void min-h-full">
      <div className="max-w-xl mx-auto">
        <Link
          to="/app/home"
          className="inline-flex items-center gap-1.5 text-[12px] text-saibyl-muted hover:text-saibyl-platinum transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Your products
        </Link>

        <h1 className="text-h1 text-saibyl-white mt-3">New product</h1>
        <p className="text-[13px] text-saibyl-muted mt-1.5 leading-relaxed">
          A product is whatever you are trying to sell. Next you will upload the
          deck or the landing page, and we will work out who buys it.
        </p>

        <div className="glass rounded-2xl p-6 mt-6 space-y-5">
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

          <Guarded
            label="Create it"
            onClick={create}
            busy={saving}
            busyLabel="Creating…"
          />
        </div>
      </div>
    </div>
  );
}
