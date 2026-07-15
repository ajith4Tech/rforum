/**
 * Cycle a list index on ArrowUp/ArrowDown, wrapping at the ends. Returns the
 * new index, or null if `key` isn't an arrow key or the list is empty (caller
 * keeps its current activeIndex unchanged).
 */
export function cycleSearchIndex(key: string, activeIndex: number, length: number): number | null {
  if (length === 0) return null;
  if (key === 'ArrowDown') return (activeIndex + 1) % length;
  if (key === 'ArrowUp') return activeIndex <= 0 ? length - 1 : activeIndex - 1;
  return null;
}
