import { create } from 'zustand';
import api from '@/lib/api';

interface User {
  id: string;
  email: string;
}

interface Organization {
  id: string;
  name: string;
  slug: string;
  plan: string;
}

interface AuthState {
  user: User | null;
  org: Organization | null;
  role: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, orgName: string) => Promise<void>;
  logout: () => void;
  loadSession: () => Promise<void>;
}

const SESSION_MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours

function isSessionExpired(): boolean {
  const ts = localStorage.getItem('saibyl_session_ts');
  if (!ts) return true;
  return Date.now() - parseInt(ts, 10) > SESSION_MAX_AGE_MS;
}

function clearSession() {
  localStorage.removeItem('saibyl_access_token');
  localStorage.removeItem('saibyl_refresh_token');
  localStorage.removeItem('saibyl_session_ts');
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  org: null,
  role: null,
  isAuthenticated: false,
  isLoading: true,

  login: async (email, password) => {
    const { data } = await api.post('/auth/login', { email, password });
    localStorage.setItem('saibyl_access_token', data.access_token);
    localStorage.setItem('saibyl_refresh_token', data.refresh_token);
    localStorage.setItem('saibyl_session_ts', Date.now().toString());

    const me = await api.get('/auth/me');
    set({
      user: me.data.user,
      org: me.data.organization,
      role: me.data.role,
      isAuthenticated: true,
      isLoading: false,
    });
  },

  signup: async (email, password, orgName) => {
    await api.post('/auth/signup', { email, password, org_name: orgName });
    // Auto-login after signup
    await get().login(email, password);
  },

  logout: () => {
    api.post('/auth/logout').catch(() => {});
    clearSession();
    set({ user: null, org: null, role: null, isAuthenticated: false, isLoading: false });
  },

  loadSession: async () => {
    const token = localStorage.getItem('saibyl_access_token');
    if (!token || isSessionExpired()) {
      clearSession();
      set({ isLoading: false });
      return;
    }
    try {
      const me = await api.get('/auth/me');
      set({
        user: me.data.user,
        org: me.data.organization,
        role: me.data.role,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch {
      clearSession();
      set({ user: null, org: null, role: null, isAuthenticated: false, isLoading: false });
    }
  },
}));
