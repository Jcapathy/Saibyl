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

// Follow 307 redirects for POST/PATCH/DELETE by retrying with the redirect URL
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const { config, response } = error;
    if (response?.status === 307 && config && !config._retried) {
      const location = response.headers?.location;
      if (location) {
        config._retried = true;
        // Use the redirect location — could be relative or absolute
        if (location.startsWith('http')) {
          config.url = location;
          config.baseURL = '';
        } else {
          config.url = location;
          config.baseURL = '';
          // Prepend origin for absolute path
          config.url = window.location.origin + location;
        }
        return api.request(config);
      }
    }
    if (response?.status === 401) {
      const hadToken = config?.headers?.Authorization;
      if (hadToken) {
        localStorage.removeItem('saibyl_access_token');
      }
    }
    return Promise.reject(error);
  }
);

export default api;
