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

// Handle 401 — clear token silently
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      const hadToken = error.config?.headers?.Authorization;
      if (hadToken) {
        localStorage.removeItem('saibyl_access_token');
      }
    }
    return Promise.reject(error);
  }
);

export default api;
