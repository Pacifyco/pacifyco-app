import type { LucideIcon } from "lucide-react";

// design.md sections 7 and 10: 28px icon on a 64px peach disc in coral-deep, always with a visible label.
export function IconTile({ icon: Icon, label }: { icon: LucideIcon; label: string }) {
  return (
    <div className="flex flex-col items-start gap-3">
      <span className="flex size-[64px] items-center justify-center rounded-pill bg-surface-tint text-coral-deep">
        <Icon aria-hidden="true" size={28} strokeWidth={1.75} />
      </span>
      <span className="text-ui text-ink">{label}</span>
    </div>
  );
}
