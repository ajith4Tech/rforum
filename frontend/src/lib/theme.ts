import { writable } from 'svelte/store';

type Theme = 'light' | 'dark';

function getInitialTheme(): Theme {
  if (typeof localStorage === 'undefined') return 'dark';
  const stored = localStorage.getItem('rforum_theme');
  if (stored === 'light' || stored === 'dark') return stored;
  return 'dark';
}

export const theme = writable<Theme>(getInitialTheme());

theme.subscribe((value) => {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem('rforum_theme', value);
  }
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', value);
  }
});

export function toggleTheme() {
  theme.update((current) => (current === 'light' ? 'dark' : 'light'));
}
