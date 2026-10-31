import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import {
  applyTheme,
  getStoredPreference,
  resolveTheme,
  storePreference,
  watchSystemTheme,
  type ResolvedTheme,
  type ThemePreference,
} from "./theme";

type ThemeContextValue = {
  preference: ThemePreference;
  theme: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(getStoredPreference);
  const [theme, setTheme] = useState<ResolvedTheme>(() => resolveTheme(preference));

  useEffect(() => {
    const update = () => {
      const resolved = resolveTheme(preference);
      setTheme(resolved);
      applyTheme(resolved);
    };
    update();
    // Only follow OS changes while the preference is "system".
    return preference === "system" ? watchSystemTheme(update) : undefined;
  }, [preference]);

  const setPreference = (next: ThemePreference) => {
    storePreference(next);
    setPreferenceState(next);
  };

  return <ThemeContext.Provider value={{ preference, theme, setPreference }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider");
  return value;
}
