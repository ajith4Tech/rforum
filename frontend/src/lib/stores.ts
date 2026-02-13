import { writable } from 'svelte/store';

export const token = writable<string | null>(
  typeof localStorage !== 'undefined' ? localStorage.getItem('rforum_token') : null
);

token.subscribe((value) => {
  if (typeof localStorage !== 'undefined') {
    if (value) localStorage.setItem('rforum_token', value);
    else localStorage.removeItem('rforum_token');
  }
});

export const currentSession = writable<any>(null);
export const activeSlide = writable<any>(null);
export const responses = writable<any[]>([]);
