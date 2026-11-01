import { Siren } from "lucide-react";
import { useId, useState } from "react";

// design.md section 10: always visible on active bookings, chocolate surface (not coral), clear label,
// and a confirmation step so it isn't pressed by accident. Pressing confirm raises an incident (CLAUDE.md 6.9).
type EmergencyButtonProps = {
  onConfirm: () => void;
  /** True while the report is being sent. */
  sending?: boolean;
};

export function EmergencyButton({ onConfirm, sending = false }: EmergencyButtonProps) {
  const [confirming, setConfirming] = useState(false);
  const headingId = useId();

  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className="inline-flex w-full items-center justify-center gap-2 rounded-pill bg-surface-inverse px-5 py-3 text-ui text-surface-default sm:w-auto"
      >
        <Siren aria-hidden="true" size={22} strokeWidth={1.75} />
        Emergency or report
      </button>
    );
  }

  return (
    <section
      role="alertdialog"
      aria-labelledby={headingId}
      className="flex flex-col gap-4 rounded-lg bg-surface-inverse p-5 text-surface-default"
    >
      <h2 id={headingId} className="text-h3">
        Alert the Pacify team now?
      </h2>
      <p className="text-body">
        We'll be told straight away and will call you. If anyone is in danger, call 112 first.
      </p>
      <div className="flex flex-col gap-3 sm:flex-row">
        <button
          type="button"
          onClick={onConfirm}
          disabled={sending}
          aria-busy={sending || undefined}
          autoFocus
          className="inline-flex w-full items-center justify-center rounded-pill bg-surface-default px-5 py-3 text-ui text-ink disabled:opacity-60 sm:w-auto"
        >
          {sending ? "Alerting the team…" : "Yes, alert Pacify"}
        </button>
        <button
          type="button"
          onClick={() => setConfirming(false)}
          disabled={sending}
          className="inline-flex w-full items-center justify-center rounded-pill border border-surface-default px-5 py-3 text-ui text-surface-default disabled:opacity-60 sm:w-auto"
        >
          Cancel
        </button>
      </div>
    </section>
  );
}
