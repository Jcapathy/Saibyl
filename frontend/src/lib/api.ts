import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  headers: { 'Content-Type': 'application/json' },
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

export default api;
