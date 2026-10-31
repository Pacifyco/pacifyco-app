import type { ReactNode } from "react";

// design.md section 10: one empathetic line, one helpful action.
export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-5 rounded-lg bg-surface-sunken p-6">
      <p className="max-w-[62ch] text-body-lg text-ink">{message}</p>
      {action}
    </div>
  );
}
