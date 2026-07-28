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

// ── Organization Settings / Branding ──────────────────
// Defaults mirror app/models.py::DEFAULT_ORG_DISPLAY_NAME and the bundled
// static assets — populated once from GET /api/settings/org on root layout
// mount (see routes/+layout.svelte), so pages never show a loading flash.
export interface OrgSettingsPublic {
  display_name: string;
  logo_url: string;
  favicon_url: string;
  updated_at: string | null;
}

export const orgSettings = writable<OrgSettingsPublic>({
  display_name: 'Your Organization',
  logo_url: '/logo-mascot.webp',
  favicon_url: '/favicon.ico',
  updated_at: null
});
