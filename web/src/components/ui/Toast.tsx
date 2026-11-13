import { CircleCheck } from "lucide-react";
import { useEffect, useSyncExternalStore } from "react";

// design.md 12: a toast at the bottom for "Saved". One at a time; it stays across page changes (the
// layout holds it), so "Details saved" still shows after the page sends people back to their profile.

type Toast = { id: number; message: string };

let current: Toast | null = null;
let nextId = 1;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

/** Shows a short confirmation, e.g. "Details saved". */
export function showToast(message: string) {
  current = { id: nextId++, message };
  emit();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

const SHOWN_MS = 4000;

export function Toaster() {
  const toast = useSyncExternalStore(
    subscribe,
    () => current,
    () => null,
  );

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => {
      if (current?.id === toast.id) {
        current = null;
        emit();
      }
    }, SHOWN_MS);
    return () => clearTimeout(timer);
  }, [toast]);

  return (
    <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-5 z-30 flex justify-center px-4">
      {toast && (
        <p
          key={toast.id}
          role="status"
          className="bubble-in flex items-center gap-2 rounded-pill bg-surface-inverse px-5 py-3 text-ui text-surface-default shadow-lift"
        >
          <CircleCheck aria-hidden="true" size={20} strokeWidth={1.75} />
          {toast.message}
        </p>
      )}
    </div>
  );
}
