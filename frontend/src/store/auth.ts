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
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, orgName: string) => Promise<void>;
  logout: () => void;
  loadSession: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  org: null,
  role: null,
  token: localStorage.getItem('saibyl_access_token'),
  isLoading: true,

  login: async (email, password) => {
    const { data } = await api.post('/auth/login', { email, password });
    localStorage.setItem('saibyl_access_token', data.access_token);
    set({ token: data.access_token });
    // Load user info
    const me = await api.get('/auth/me');
    set({ user: me.data.user, org: me.data.organization, role: me.data.role, isLoading: false });
  },

  signup: async (email, password, orgName) => {
    await api.post('/auth/signup', { email, password, org_name: orgName });
    // Auto-login after signup
    const { data } = await api.post('/auth/login', { email, password });
    localStorage.setItem('saibyl_access_token', data.access_token);
    set({ token: data.access_token });
    const me = await api.get('/auth/me');
    set({ user: me.data.user, org: me.data.organization, role: me.data.role, isLoading: false });
  },

  logout: () => {
    localStorage.removeItem('saibyl_access_token');
    set({ user: null, org: null, role: null, token: null });
    window.location.href = '/login';
  },

  loadSession: async () => {
    const token = localStorage.getItem('saibyl_access_token');
    if (!token) {
      set({ isLoading: false });
      return;
    }
    try {
      const me = await api.get('/auth/me');
      set({ user: me.data.user, org: me.data.organization, role: me.data.role, isLoading: false });
    } catch {
      localStorage.removeItem('saibyl_access_token');
      set({ user: null, org: null, role: null, token: null, isLoading: false });
    }
  },
}));
