import { BarChart3, MessageSquare, Cloud, AlignLeft, Star, HelpCircle, ListChecks, Sliders, ClipboardList, Video } from 'lucide-svelte';

export interface TimelineTypeMeta {
  icon: typeof BarChart3;
  label: string;
  dot: string;
  ring: string;
}

/** Icon/label/color per interaction type, shared by the timeline sidebar and editor toolbar so the two never drift. */
export const TIMELINE_TYPE_META: Record<string, TimelineTypeMeta> = {
  POLL: { icon: BarChart3, label: 'Poll', dot: 'bg-purple-500', ring: 'border-purple-300 dark:border-purple-700 bg-purple-50 dark:bg-purple-500/10' },
  MULTIPLE_CHOICE: { icon: ListChecks, label: 'Multiple Choice', dot: 'bg-indigo-500', ring: 'border-indigo-300 dark:border-indigo-700 bg-indigo-50 dark:bg-indigo-500/10' },
  QUIZ: { icon: HelpCircle, label: 'Quiz', dot: 'bg-violet-500', ring: 'border-violet-300 dark:border-violet-700 bg-violet-50 dark:bg-violet-500/10' },
  QNA: { icon: MessageSquare, label: 'Q&A', dot: 'bg-sky-500', ring: 'border-sky-300 dark:border-sky-700 bg-sky-50 dark:bg-sky-500/10' },
  WORD_CLOUD: { icon: Cloud, label: 'Word Cloud', dot: 'bg-emerald-500', ring: 'border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-500/10' },
  FEEDBACK: { icon: AlignLeft, label: 'Feedback', dot: 'bg-rose-500', ring: 'border-rose-300 dark:border-rose-700 bg-rose-50 dark:bg-rose-500/10' },
  RATING: { icon: Star, label: 'Rating', dot: 'bg-amber-500', ring: 'border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-500/10' },
  SCALE: { icon: Sliders, label: 'Scale', dot: 'bg-teal-500', ring: 'border-teal-300 dark:border-teal-700 bg-teal-50 dark:bg-teal-500/10' },
  SURVEY: { icon: ClipboardList, label: 'Survey', dot: 'bg-orange-500', ring: 'border-orange-300 dark:border-orange-700 bg-orange-50 dark:bg-orange-500/10' },
  VIDEO: { icon: Video, label: 'Video', dot: 'bg-red-500', ring: 'border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-500/10' },
};

const PAGE_META: TimelineTypeMeta = {
  icon: AlignLeft,
  label: 'Page',
  dot: 'bg-slate-400',
  ring: 'border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-500/10',
};

/** Resolves a timeline item's display metadata, handling interaction primitives and layout types. */
export function metaForItem(item: any): TimelineTypeMeta {
  if (item?.item_type === 'PAGE') return PAGE_META;
  const slide = item?.slide || item;
  const cj = slide?.content_json || {};
  const itype = (cj.interaction_type || cj.mode || '').toUpperCase();
  if (itype === 'QUIZ') return TIMELINE_TYPE_META.QUIZ;
  if (itype === 'MULTIPLE_CHOICE') return TIMELINE_TYPE_META.MULTIPLE_CHOICE;
  if (itype === 'SCALE') return TIMELINE_TYPE_META.SCALE;
  if (itype === 'SURVEY') return TIMELINE_TYPE_META.SURVEY;
  if (itype === 'RATING_ONLY' || item?.item_type === 'RATING' || (slide?.type === 'FEEDBACK' && cj.mode === 'rating_only')) return TIMELINE_TYPE_META.RATING;
  if (cj.layout === 'video' || slide?.type === 'VIDEO') return TIMELINE_TYPE_META.VIDEO;
  if (item?.item_type && TIMELINE_TYPE_META[item.item_type]) return TIMELINE_TYPE_META[item.item_type];
  if (slide?.type && TIMELINE_TYPE_META[slide.type]) return TIMELINE_TYPE_META[slide.type];
  return TIMELINE_TYPE_META.FEEDBACK;
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
