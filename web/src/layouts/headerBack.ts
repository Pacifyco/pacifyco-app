import { createContext, useContext, useEffect } from "react";

// The page's "Back" link, also shown in the pinned header once the page is scrolled (Reuben, 2026-11-13:
// on an iPhone in the Google app, the app's search bar covered the logo and Back at the top). A page's
// BackLink registers itself here; the header shows it only after scrolling, so it's never shown twice.

export type BackTarget = { label: string; to?: string; onBack?: () => void };

export const HeaderBackContext = createContext<(target: BackTarget | null) => void>(() => {});

export function useHeaderBack(target: BackTarget | null) {
  const register = useContext(HeaderBackContext);
  const label = target?.label;
  const to = target?.to;
  const onBack = target?.onBack;
  useEffect(() => {
    if (!label) return;
    register({ label, to, onBack });
    return () => register(null);
  }, [register, label, to, onBack]);
}
