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
  logout: () => Promise<void>;
  loadSession: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  org: null,
  role: null,
  isAuthenticated: false,
  isLoading: true,

  login: async (email, password) => {
    await api.post('/auth/login', { email, password });
    // Cookie is set by the server — now fetch user info
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
    // Signup sets cookies too — fetch user info
    const me = await api.get('/auth/me');
    set({
      user: me.data.user,
      org: me.data.organization,
      role: me.data.role,
      isAuthenticated: true,
      isLoading: false,
    });
  },

  logout: async () => {
    try {
      await api.post('/auth/logout');
    } catch {
      // Server might be unreachable — clear local state anyway
    }
    set({ user: null, org: null, role: null, isAuthenticated: false, isLoading: false });
  },

  loadSession: async () => {
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
      set({ user: null, org: null, role: null, isAuthenticated: false, isLoading: false });
    }
  },
}));
