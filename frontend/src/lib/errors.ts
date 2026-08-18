import { AxiosError } from 'axios';

/**
 * Extract a human-readable message from an unknown thrown value.
 *
 * The backend returns FastAPI-style `{ detail: string }` bodies, but `detail`
 * is an array of validation objects for 422s, so both shapes are handled.
 */
export function getErrorMessage(err: unknown, fallback = 'Something went wrong'): string {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail;

    if (typeof detail === 'string' && detail.trim()) return detail;

    // FastAPI validation errors: [{ loc, msg, type }, ...]
    if (Array.isArray(detail)) {
      const messages = detail
        .map((d) => (typeof d === 'string' ? d : d?.msg))
        .filter((m): m is string => typeof m === 'string' && m.trim().length > 0);
      if (messages.length) return messages.join('; ');
    }

    /*
      Axios' own message is not a sentence for a founder.

      With no backend exception handler, a 500 arrives as Starlette's default
      `PlainTextResponse("Internal Server Error")` — no JSON body, so neither
      `detail` branch above matches and this line returned "Request failed
      with status code 500". That shadowed the written fallback at roughly 65
      call sites: every carefully worded "We could not load your reports."
      was dead code on exactly the failure it was written for.

      So the transport's message is used only when it says something a reader
      can act on — a genuine network failure — and everything else falls
      through to the caller's sentence.
    */
    if (!err.response && err.message) return err.message;
  }

  if (err instanceof Error && err.message && !(err instanceof AxiosError)) {
    return err.message;
  }

  return fallback;
}
