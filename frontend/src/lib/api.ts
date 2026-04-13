import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

// Handle 401 — try cookie-based refresh, then redirect to login
let isRefreshing = false;
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401 && !error.config._retry) {
      if (!isRefreshing) {
        isRefreshing = true;
        error.config._retry = true;
        try {
          await api.post('/auth/refresh');
          return api(error.config);
        } catch {
          window.location.href = '/login';
        } finally {
          isRefreshing = false;
        }
      }
    }
    return Promise.reject(error);
  }
);

export default api;
