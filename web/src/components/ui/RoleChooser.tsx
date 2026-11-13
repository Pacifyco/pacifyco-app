import { CircleCheck, HeartHandshake, House, type LucideIcon } from "lucide-react";
import { cx } from "./cx";
import { Photo, type PhotoName } from "./Photo";

export type ChosenRole = "parent" | "sitter";

const OPTIONS: { role: ChosenRole; label: string; detail: string; icon: LucideIcon; photo: PhotoName }[] = [
  {
    role: "parent",
    label: "I'm a parent",
    detail: "Find a sitter and meet them first.",
    icon: House,
    photo: "parentsDinnerFriends",
  },
  {
    role: "sitter",
    label: "I'm a sitter",
    detail: "Care is skilled work. Join the Pacifyco team.",
    icon: HeartHandshake,
    photo: "sitterHomePlay",
  },
];

// design.md section 10: "I'm a parent" / "I'm a sitter". Admins are never chosen here (CLAUDE.md 2).
// Side by side and compact on phones (no photo), with a tick and a coral border when chosen (UX review
// 2026-11-13).
export function RoleChooser({ value, onChange }: { value: ChosenRole | null; onChange: (role: ChosenRole) => void }) {
  return (
    <div role="group" aria-label="Choose how you'll use Pacifyco" className="grid grid-cols-2 gap-3 sm:gap-4">
      {OPTIONS.map(({ role, label, detail, icon: Icon, photo }) => {
        const selected = value === role;
        return (
          <button
            key={role}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(role)}
            className={cx(
              "relative flex flex-col gap-3 rounded-lg bg-surface-raised p-4 text-left shadow-soft transition duration-200 ease-calm hover:shadow-lift sm:gap-4 sm:p-5",
              selected ? "border-2 border-coral" : "border-2 border-transparent",
            )}
          >
            {selected && (
              <CircleCheck
                aria-hidden="true"
                size={24}
                strokeWidth={1.75}
                className="absolute top-3 right-3 z-10 rounded-pill bg-surface-raised text-coral-deep"
              />
            )}
            <Photo
              name={photo}
              aspect="3 / 2"
              sizes="(min-width: 640px) 20rem, 100vw"
              className="hidden rounded-md shadow-none sm:block"
            />
            <span className="flex flex-col items-start gap-3 sm:flex-row sm:gap-4">
              <span className="flex size-[48px] shrink-0 items-center justify-center rounded-pill bg-surface-tint text-coral-deep sm:size-[64px]">
                <Icon aria-hidden="true" size={24} strokeWidth={1.75} />
              </span>
              <span className="flex flex-col gap-1">
                <span className="text-ui text-ink">{label}</span>
                <span className="text-small text-muted">{detail}</span>
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
