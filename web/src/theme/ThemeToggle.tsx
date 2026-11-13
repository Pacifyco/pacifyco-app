import { useTheme } from "./ThemeProvider";
import type { ResolvedTheme } from "./theme";

// Two choices, light and dark (decided 2026-11-09: sun and moon, no words, no "System" button).
// Until someone picks one, the app follows the phone's setting and the matching option shows as on.
const OPTIONS: { value: ResolvedTheme; emoji: string; label: string }[] = [
  { value: "light", emoji: "☀️", label: "Light theme" },
  { value: "dark", emoji: "🌙", label: "Dark theme" },
];

export function ThemeToggle() {
  const { theme, setPreference } = useTheme();

  return (
    <div role="group" aria-label="Theme" className="flex items-center gap-1 rounded-pill border border-line p-1">
      {OPTIONS.map((option) => {
        const selected = theme === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={selected}
            aria-label={option.label}
            title={option.label}
            onClick={() => setPreference(option.value)}
            className={`flex size-[44px] items-center justify-center rounded-pill text-[1.15rem] leading-none transition-[background-color,opacity] duration-200 ease-calm ${
              selected ? "bg-surface-tint" : "opacity-50 hover:opacity-100"
            }`}
          >
            <span aria-hidden="true">{option.emoji}</span>
          </button>
        );
      })}
    </div>
  );
}
