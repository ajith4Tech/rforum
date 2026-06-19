import { writable } from 'svelte/store';

export interface Branding {
  org_name: string;
  logo_url: string;
  invite_required: boolean;
  onboarding_locked: boolean;
}

const DEFAULTS: Branding = {
  org_name: 'Tech4Good Community',
  logo_url: '/logo-mascot.webp',
  invite_required: true,
  onboarding_locked: true,
};

export const branding = writable<Branding>(DEFAULTS);

let _loaded = false;

export async function loadBranding(): Promise<void> {
  if (typeof window === 'undefined') return; // SSR guard
  if (_loaded) return;
  try {
    const res = await fetch('/api/settings/public');
    if (!res.ok) return;
    const data = await res.json();
    branding.set({
      org_name: data.org_name || DEFAULTS.org_name,
      logo_url: data.org_logo_url || DEFAULTS.logo_url,
      invite_required: data.invite_required ?? DEFAULTS.invite_required,
      onboarding_locked: data.onboarding_locked ?? DEFAULTS.onboarding_locked,
    });
    _loaded = true;
  } catch {
    // silently keep defaults
  }
}

export function resetBrandingCache(): void {
  _loaded = false;
}
