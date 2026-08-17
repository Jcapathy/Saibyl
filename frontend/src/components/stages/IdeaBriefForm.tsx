import { useState } from 'react';

import api from '@/lib/api';
import { getErrorMessage } from '@/lib/errors';
import type { ProjectDocument } from '@/types';
import { Guarded, StageError } from '@/components/stages/StagePrimitives';

/**
 * The way in for a founder who has nothing to upload.
 *
 * Step 1 works by reading what the founder has written, which quietly assumes
 * something has been written. A founder with only an idea was shown an upload
 * control and a dead end. These five questions are the material that founder
 * already has — in their head — and the backend turns the answers into a
 * document that is read exactly like an uploaded deck, so everything after
 * this point works unchanged.
 *
 * The questions are the questions, not a form schema made polite. They are the
 * five things every buyer and investor asks anyway, which is why the form ends
 * by saying so: the answers are worth writing down even if nothing here ever
 * runs.
 */

type BriefField = 'problem' | 'who' | 'solution' | 'alternatives' | 'price';

const QUESTIONS: { field: BriefField; ask: string; help: string }[] = [
  {
    field: 'problem',
    ask: 'What’s the problem?',
    help: 'One or two sentences — the pain in plain words.',
  },
  {
    field: 'who',
    ask: 'Who has it?',
    help: 'The person, not the market. “Freelance designers who invoice clients”, not “the design industry”.',
  },
  {
    field: 'solution',
    ask: 'What are you building?',
    help: 'What it does for that person.',
  },
  {
    field: 'alternatives',
    ask: 'What do they do today?',
    help: 'How they cope now — a rival, a spreadsheet, nothing.',
  },
  {
    field: 'price',
    ask: 'What would you charge?',
    help: 'A rough number is fine. A guess beats a blank.',
  },
];

/** What the backend accepts per answer. */
const LIMIT = 2000;
/** The count only appears once it could plausibly matter. A counter on an
 *  empty box reads as a demand for length, which is the opposite of the ask. */
const SHOW_REMAINING_AT = 200;

const EMPTY_ANSWERS: Record<BriefField, string> = {
  problem: '',
  who: '',
  solution: '',
  alternatives: '',
  price: '',
};

export default function IdeaBriefForm({
  productId,
  onCreated,
}: {
  productId: string;
  /** The document the backend wrote from the answers. The caller refreshes its
   *  list with this, the same way it does after an upload. */
  onCreated: (doc: ProjectDocument) => void;
}) {
  const [answers, setAnswers] = useState(EMPTY_ANSWERS);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const textareaBase =
    'w-full rounded-xl bg-white border border-saibyl-border-light px-3 py-2.5 text-[13.5px] text-saibyl-ink placeholder:text-saibyl-muted/70 focus:outline-none focus:border-saibyl-blue focus:ring-2 focus:ring-saibyl-blue/20 resize-y';

  async function submit() {
    // Stated rather than enforced by a greyed-out control: the founder gets a
    // sentence naming the box that still needs words.
    const missing = QUESTIONS.find((q) => !answers[q.field].trim());
    if (missing) {
      setError(`“${missing.ask}” still needs an answer — rough is fine, blank is not.`);
      return;
    }
    setSaving(true);
    setError('');
    try {
      const { data } = await api.post<ProjectDocument>('/documents/idea-brief', {
        project_id: productId,
        problem: answers.problem.trim(),
        who: answers.who.trim(),
        solution: answers.solution.trim(),
        alternatives: answers.alternatives.trim(),
        price: answers.price.trim(),
      });
      onCreated(data);
    } catch (err) {
      setError(getErrorMessage(err, 'We could not save your answers.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-xl border border-saibyl-border bg-saibyl-elevated p-5 space-y-5">
      <div>
        <h3 className="text-[14px] font-medium text-saibyl-platinum">
          Five short questions
        </h3>
        <p className="text-[12px] text-saibyl-muted mt-1 leading-relaxed">
          A sentence or two each is plenty. We turn your answers into your first
          document and read it the same way we would read a deck.
        </p>
      </div>

      {QUESTIONS.map((q) => {
        const value = answers[q.field];
        const remaining = LIMIT - value.length;
        return (
          <div key={q.field}>
            <label
              htmlFor={`idea-${q.field}`}
              className="block text-[12.5px] text-saibyl-silver"
            >
              {q.ask}
            </label>
            <p className="text-[11px] text-saibyl-muted/70 mt-0.5 mb-1.5 leading-relaxed">
              {q.help}
            </p>
            <textarea
              id={`idea-${q.field}`}
              rows={2}
              maxLength={LIMIT}
              value={value}
              onChange={(e) =>
                setAnswers((prev) => ({ ...prev, [q.field]: e.target.value }))
              }
              className={textareaBase}
            />
            {remaining <= SHOW_REMAINING_AT && (
              <p className="text-[11px] text-saibyl-muted/70 mt-1">
                {remaining} characters left
              </p>
            )}
          </div>
        );
      })}

      {error && <StageError message={error} />}

      <div>
        <Guarded
          label="Build my audience from this"
          onClick={submit}
          busy={saving}
          busyLabel="Saving your answers…"
        />
        <p className="text-[11px] text-saibyl-muted/60 mt-3 leading-relaxed">
          These five are the same five questions every buyer and investor will
          ask you — sharp answers are worth having whether or not you ever start
          the run.
        </p>
      </div>
    </div>
  );
}
