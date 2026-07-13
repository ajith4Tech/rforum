import { BarChart3, MessageSquare, Cloud, AlignLeft, Star } from 'lucide-svelte';

export interface TimelineTypeMeta {
  icon: typeof BarChart3;
  label: string;
  dot: string;
  ring: string;
}

/** Icon/label/color per interaction type, shared by the timeline sidebar and editor toolbar so the two never drift. */
export const TIMELINE_TYPE_META: Record<string, TimelineTypeMeta> = {
  POLL: { icon: BarChart3, label: 'Poll', dot: 'bg-purple-500', ring: 'border-purple-300 dark:border-purple-700 bg-purple-50 dark:bg-purple-500/10' },
  QNA: { icon: MessageSquare, label: 'Q&A', dot: 'bg-sky-500', ring: 'border-sky-300 dark:border-sky-700 bg-sky-50 dark:bg-sky-500/10' },
  WORD_CLOUD: { icon: Cloud, label: 'Word Cloud', dot: 'bg-emerald-500', ring: 'border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-500/10' },
  FEEDBACK: { icon: AlignLeft, label: 'Feedback', dot: 'bg-rose-500', ring: 'border-rose-300 dark:border-rose-700 bg-rose-50 dark:bg-rose-500/10' },
  RATING: { icon: Star, label: 'Rating', dot: 'bg-amber-500', ring: 'border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-500/10' },
};

const PAGE_META: TimelineTypeMeta = {
  icon: AlignLeft,
  label: 'Page',
  dot: 'bg-slate-400',
  ring: 'border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-500/10',
};

/** Resolves a timeline item's display metadata, handling the RATING-is-really-a-FEEDBACK-slide special case. */
export function metaForItem(item: any): TimelineTypeMeta {
  if (item.item_type === 'PAGE') return PAGE_META;
  if (item.item_type !== 'FEEDBACK') return TIMELINE_TYPE_META[item.item_type] || TIMELINE_TYPE_META.FEEDBACK;
  return item.slide?.content_json?.mode === 'rating_only' ? TIMELINE_TYPE_META.RATING : TIMELINE_TYPE_META.FEEDBACK;
}

/**
 * Folds a `slide_change` WebSocket payload into a guest/screen client's local
 * timeline item list. A guest who joined before an interaction was inserted
 * has no local copy of it — activation only broadcasts the activated item's
 * own data, never a full timeline refetch — so without this upsert, activating
 * a brand-new item would leave `active_timeline_item_id` pointing at an id
 * missing from `items`, and the guest would see "waiting for presenter"
 * instead of the interaction.
 */
export function upsertTimelineItemFromWs(items: any[], msgData: any): any[] {
  const id = msgData?.timeline_item_id;
  if (!id) return items;
  const patch = { id, item_type: msgData.item_type, page: msgData.page ?? null, slide: msgData.slide ?? null };
  const idx = items.findIndex((i) => i.id === id);
  if (idx === -1) {
    return [...items, { order: items.length, ...patch }];
  }
  return items.map((i) => (i.id === id ? { ...i, ...patch } : i));
}
