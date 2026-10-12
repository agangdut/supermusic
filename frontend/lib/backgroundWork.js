// Tiny shared store for "work still running" counts, so any page can show
// the "safe to switch" notice. Each source (workspace jobs, map import) sets its own count.
import { useEffect, useState } from "react";

const counts = {};
const listeners = new Set();

export function setBackgroundWork(source, count) {
  if ((counts[source] || 0) === count) return;
  counts[source] = count;
  listeners.forEach((fn) => fn({ ...counts }));
}

export function useBackgroundWork() {
  const [state, setState] = useState(() => ({ ...counts }));
  useEffect(() => {
    listeners.add(setState);
    setState({ ...counts });
    return () => listeners.delete(setState);
  }, []);
  return state;
}
