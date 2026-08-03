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

    if (err.message) return err.message;
  }

  if (err instanceof Error && err.message) return err.message;

  return fallback;
}
