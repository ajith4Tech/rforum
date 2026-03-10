import { writable, derived } from 'svelte/store';

export const token = writable<string | null>(
  typeof localStorage !== 'undefined' ? localStorage.getItem('rforum_token') : null
);

token.subscribe((value) => {
  if (typeof localStorage !== 'undefined') {
    if (value) localStorage.setItem('rforum_token', value);
    else localStorage.removeItem('rforum_token');
  }
});

export interface CurrentUser {
  id: string;
  email: string;
  role: 'USER' | 'SUPER_ADMIN';
  is_active: boolean;
  created_at: string;
}

export const currentUser = writable<CurrentUser | null>(null);
export const isSuperAdmin = derived(currentUser, ($u) => $u?.role === 'SUPER_ADMIN');

export const currentSession = writable<any>(null);
export const activeSlide = writable<any>(null);
export const responses = writable<any[]>([]);
