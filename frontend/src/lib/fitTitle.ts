/** Shared title/question sizing for 16:9 presentation surfaces. */
export function getFitTitleStyle(text: string, type: 'title' | 'question' = 'title'): string {
  const len = (text || '').trim().length;
  if (!len) return '';
  if (type === 'question') {
    if (len < 30) return 'font-size: clamp(1.35rem, 3vw, 2.2rem); line-height: 1.15; word-break: break-word; overflow-wrap: anywhere;';
    if (len < 70) return 'font-size: clamp(1.1rem, 2.4vw, 1.8rem); line-height: 1.18; word-break: break-word; overflow-wrap: anywhere;';
    if (len < 120) return 'font-size: clamp(0.95rem, 1.9vw, 1.4rem); line-height: 1.24; word-break: break-word; overflow-wrap: anywhere;';
    return 'font-size: clamp(0.82rem, 1.55vw, 1.1rem); line-height: 1.28; word-break: break-word; overflow-wrap: anywhere;';
  }
  if (len < 24) return 'font-size: clamp(1.8rem, 4vw, 3rem); line-height: 1.1; word-break: break-word; overflow-wrap: anywhere;';
  if (len < 56) return 'font-size: clamp(1.35rem, 2.9vw, 2.2rem); line-height: 1.15; word-break: break-word; overflow-wrap: anywhere;';
  if (len < 110) return 'font-size: clamp(1.05rem, 2vw, 1.55rem); line-height: 1.22; word-break: break-word; overflow-wrap: anywhere;';
  return 'font-size: clamp(0.85rem, 1.55vw, 1.1rem); line-height: 1.28; word-break: break-word; overflow-wrap: anywhere;';
}

export function mergeResponsesById(existing: any[], incoming: any[]): any[] {
  const byId = new Map(existing.map((r) => [r.id, r]));
  for (const item of incoming) {
    if (item?.id) byId.set(item.id, item);
  }
  return Array.from(byId.values());
}

export function responsesForSlide(responses: any[], slideId: string | null | undefined): any[] {
  if (!slideId) return [];
  return responses.filter((r) => !r.slide_id || r.slide_id === slideId);
}
