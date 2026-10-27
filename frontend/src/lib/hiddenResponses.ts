import { SvelteMap } from 'svelte/reactivity';

/**
 * Guest/projector view of responses the moderator hid while the page is open.
 *
 * The server already leaves hidden responses out of every audience fetch; the
 * tracker covers a fetch that was in flight when a `response_hidden` event
 * arrived (its result could still contain the response). Each hide and each
 * fetch takes a number from one sequence: once a fetch that STARTED after a
 * hide succeeds, the server's list is authoritative for that slide and the
 * entry is dropped — so a response unhidden while this page was disconnected
 * (the `new_response` re-announcement missed) reappears after the resync.
 */
export class HiddenResponseTracker {
  private seq = 0;
  private hidden = new SvelteMap<string, { slideId: string | null; seq: number }>();

  hide(responseId: string, slideId: string | null | undefined) {
    this.hidden.set(responseId, { slideId: slideId ?? null, seq: ++this.seq });
  }

  unhide(responseId: string) {
    this.hidden.delete(responseId);
  }

  /** Call right before requesting a slide's responses; pass the result to fetchSucceeded. */
  fetchStarted(): number {
    return ++this.seq;
  }

  /** A responses fetch for `slideId` started at `startedAt` succeeded. */
  fetchSucceeded(slideId: string, startedAt: number) {
    const settled = [...this.hidden]
      .filter(([, entry]) => entry.seq < startedAt && (entry.slideId === slideId || entry.slideId === null))
      .map(([id]) => id);
    for (const id of settled) this.hidden.delete(id);
  }

  /** Filter for response lists: hides moderator-hidden responses. The
   * is_hidden flag only appears when this page runs in the moderator's own
   * signed-in browser (a common projector setup), whose fetches include them. */
  isShown = (response: any): boolean => !response?.is_hidden && !this.hidden.has(response?.id);
}
