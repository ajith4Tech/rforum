/**
 * Generic undo/redo command stack. Each entry describes how to reverse
 * (`undo`) and re-apply (`redo`) one already-completed mutation — the
 * mutation itself has already round-tripped to the server by the time it's
 * pushed here, so `undo`/`redo` just issue the compensating API call(s) and
 * update local state from the response, mirroring what the original action
 * already did.
 *
 * Entries whose action creates a server-generated id (insert/duplicate) use
 * an `IdBox` so a later undo-of-delete (which necessarily creates a NEW id)
 * keeps the paired redo entry pointing at the right row, without needing a
 * full state-snapshot/diff system.
 */

export interface UndoEntry {
  label: string;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
}

/** A mutable box for an id that may be replaced when a delete is undone
 * (re-creating the row server-side under a new id). */
export interface IdBox {
  id: string;
}

const MAX_HISTORY = 50;

export class UndoManager {
  private undoStack: UndoEntry[] = [];
  private redoStack: UndoEntry[] = [];
  private busy = false;
  onChange?: () => void;

  push(entry: UndoEntry): void {
    this.undoStack.push(entry);
    if (this.undoStack.length > MAX_HISTORY) this.undoStack.shift();
    this.redoStack = [];
    this.onChange?.();
  }

  get canUndo(): boolean {
    return this.undoStack.length > 0;
  }

  get canRedo(): boolean {
    return this.redoStack.length > 0;
  }

  get isBusy(): boolean {
    return this.busy;
  }

  async undo(): Promise<void> {
    if (this.busy) return;
    const entry = this.undoStack.pop();
    if (!entry) return;
    this.busy = true;
    this.onChange?.();
    try {
      await entry.undo();
      this.redoStack.push(entry);
    } catch (err) {
      // Put it back so a transient failure doesn't permanently drop the
      // action from history — the caller can retry the same undo.
      this.undoStack.push(entry);
      throw err;
    } finally {
      this.busy = false;
      this.onChange?.();
    }
  }

  async redo(): Promise<void> {
    if (this.busy) return;
    const entry = this.redoStack.pop();
    if (!entry) return;
    this.busy = true;
    this.onChange?.();
    try {
      await entry.redo();
      this.undoStack.push(entry);
    } catch (err) {
      this.redoStack.push(entry);
      throw err;
    } finally {
      this.busy = false;
      this.onChange?.();
    }
  }

  clear(): void {
    this.undoStack = [];
    this.redoStack = [];
    this.onChange?.();
  }
}
