import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  headers: { 'Content-Type': 'application/json' },
  /*
    Axios defaults to no timeout at all, so a request that never settles
    never runs its `finally` — bypassing every disciplined `setLoading(false)`
    in the app. The worst case is the founder's very first load: a stalled
    `/auth/me` against a cold-started Render backend leaves `ProtectedRoute`
    on a bare, textless spinner forever.

    90s is chosen against the work, not against a browser default: report
    generation and clearance runs are the long ones and both are polled
    rather than awaited, so nothing legitimate on this instance runs longer.
  */
  timeout: 90_000,
});

// Inject auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('saibyl_access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 — try refresh, then redirect to login
let isRefreshing = false;
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry) {
      const refreshToken = localStorage.getItem('saibyl_refresh_token');
      if (refreshToken && !isRefreshing) {
        isRefreshing = true;
        error.config._retry = true;
        try {
          const { data } = await axios.post(
            `${api.defaults.baseURL}/auth/refresh`,
            null,
            { params: { refresh_token: refreshToken } },
          );
          localStorage.setItem('saibyl_access_token', data.access_token);
          localStorage.setItem('saibyl_refresh_token', data.refresh_token);
          localStorage.setItem('saibyl_session_ts', Date.now().toString());
          error.config.headers.Authorization = `Bearer ${data.access_token}`;
          return api(error.config);
        } catch {
          // Refresh failed — force login
          localStorage.removeItem('saibyl_access_token');
          localStorage.removeItem('saibyl_refresh_token');
          localStorage.removeItem('saibyl_session_ts');
          window.location.href = '/login';
        } finally {
          isRefreshing = false;
        }
      } else if (!refreshToken) {
        localStorage.removeItem('saibyl_access_token');
        localStorage.removeItem('saibyl_session_ts');
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

/**
 * A paged list response from the backend.
 *
 * `total` is null when the server could not obtain an exact count — it is NOT
 * the same as zero, and it must never be inferred from `items.length`.
 * Guessing "one page" is how a pager hides the user's own work: a customer
 * with 50 simulations could never reach page 2 because `count="exact"` was
 * computed server-side and then discarded.
 */
export interface Paged<T> {
  items: T[];
  total: number | null;
  limit?: number;
  offset?: number;
}

/**
 * Read a list endpoint's body whether it arrives as a bare array or an
 * envelope.
 *
 * One helper rather than an `Array.isArray` ternary at each of the four call
 * sites: a duplicated unwrap is the "two sources of truth for one value" class,
 * and the shape only has to drift at one reader for that page to silently
 * render empty — no error, no counter, nothing to investigate.
 *
 * The bare-array branch is transitional. Delete it once every list endpoint
 * returns an envelope, and this becomes a single property read.
 */
export function unwrapList<T>(body: T[] | Paged<T> | null | undefined): Paged<T> {
  if (Array.isArray(body)) {
    return { items: body, total: body.length };
  }
  if (!body || !Array.isArray(body.items)) {
    return { items: [], total: null };
  }
  return { items: body.items, total: body.total ?? null };
}

export default api;
