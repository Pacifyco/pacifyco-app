import { useTheme } from "./ThemeProvider";
import type { ThemePreference } from "./theme";

const OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

export function ThemeToggle() {
  const { preference, setPreference } = useTheme();

  return (
    <div role="group" aria-label="Theme" className="flex items-center gap-1 rounded-pill border border-line p-1">
      {OPTIONS.map((option) => {
        const selected = preference === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            onClick={() => setPreference(option.value)}
            className={`rounded-pill px-3 py-1 text-small font-medium transition-colors duration-200 ease-calm ${
              selected ? "bg-surface-tint text-ink" : "text-muted hover:text-ink"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
