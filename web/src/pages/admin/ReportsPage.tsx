import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { BackLink, Button, Card, EmptyState, Textarea, showToast } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDay, formatMobile, formatTime } from "../../lib/format";
import { rupees } from "../../lib/prices";
import { minutesLeft } from "../../lib/reports";
import { errorMessage } from "./shared";

// Reports during a booking (CLAUDE.md 6.5): call both people, then confirm or dismiss.
// - Parent not home: the sitter may leave if no parent responds within 20 minutes. Mark it answered if the
//   parent picks up. Confirming (after the 20 minutes) closes the booking: charged in full, show-up fee due.
// - Sitter no-show: confirming refunds the parent and gives the sitter a strike.

export type AdminReport = {
  id: string;
  kind: "parent_absent" | "sitter_no_show" | "only_man_home";
  reported_at: string;
  responded_at: string | null;
  can_leave_at: string | null;
  booking_id: string;
  starts_at: string;
  ends_at: string;
  hours: number;
  parent_name: string | null;
  parent_phone: string | null;
  sitter_name: string | null;
  sitter_phone: string | null;
  show_up_fee_paise: number;
};

export const REPORTS_KEY = ["admin", "reports"];

const KIND_WORDS: Record<AdminReport["kind"], string> = {
  parent_absent: "No one home, says the sitter",
  sitter_no_show: "Sitter didn't come, says the parent",
  only_man_home: "Sitter declined: only a man at home",
};

function when(iso: string): string {
  const moment = new Date(iso);
  return `${formatDay(moment)}, ${formatTime(moment)}`;
}

function Phone({ label, name, phone }: { label: string; name: string | null; phone: string | null }) {
  return (
    <div className="flex flex-col">
      <span className="text-small text-muted">{label}</span>
      <span className="text-ink">{name ?? "Not given"}</span>
      {phone && (
        <a href={`tel:${phone}`} className="text-ui">
          {formatMobile(phone)}
        </a>
      )}
    </div>
  );
}

/** Where the 20-minute wait stands, for a parent-not-home report. */
export function waitText(report: AdminReport, now: Date): string | null {
  if (report.kind === "only_man_home") {
    return `She has declined and left. Confirming closes the booking, charged in full, and pays her ${rupees(report.show_up_fee_paise)}.`;
  }
  if (report.kind !== "parent_absent") return null;
  if (report.responded_at) return "A parent responded: the sitter waits. Dismiss it once they're together.";
  const left = report.can_leave_at ? minutesLeft(report.can_leave_at, now) : null;
  return left
    ? `No response yet. She may leave in ${left}.`
    : `No response in 20 minutes: she may leave. Confirming pays her ${rupees(report.show_up_fee_paise)}.`;
}

function ReportItem({ report }: { report: AdminReport }) {
  const queryClient = useQueryClient();
  const [dismissing, setDismissing] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | undefined>();
  const act = useMutation({
    mutationFn: (action: { path: string; note?: string }) =>
      apiFetch<AdminReport>(`/admin/reports/${report.id}/${action.path}`, {
        method: "POST",
        body: JSON.stringify({ note: action.note ?? null }),
      }),
    onSuccess: async (_, action) => {
      showToast(
        action.path === "answered" ? "Marked as answered" : action.path === "confirm" ? "Confirmed" : "Dismissed",
      );
      await queryClient.invalidateQueries({ queryKey: REPORTS_KEY });
    },
    onError: (failed) => setError(errorMessage(failed)),
  });

  function dismiss(event: FormEvent) {
    event.preventDefault();
    if (!note.trim()) return setError("Please say why you're dismissing it.");
    setError(undefined);
    act.mutate({ path: "dismiss", note: note.trim() });
  }

  const wait = waitText(report, new Date());
  return (
    <li className="flex flex-col gap-4 border-t border-line py-5 first:border-t-0">
      <div className="flex flex-col gap-1">
        <p className="text-eyebrow text-muted uppercase">{KIND_WORDS[report.kind]}</p>
        <p className="text-ui text-ink">
          Booking {when(report.starts_at)} – {formatTime(new Date(report.ends_at))} · reported {when(report.reported_at)}
        </p>
        {wait && <p className="text-ink">{wait}</p>}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Phone label="Parent" name={report.parent_name} phone={report.parent_phone} />
        <Phone label="Sitter" name={report.sitter_name} phone={report.sitter_phone} />
      </div>
      {dismissing ? (
        <form noValidate onSubmit={dismiss} className="flex flex-col gap-3">
          <Textarea
            label="Why are you dismissing it?"
            hint="Both of them are told the booking goes ahead."
            rows={2}
            maxLength={500}
            value={note}
            error={error}
            onChange={(event) => setNote(event.target.value)}
          />
          <div className="flex flex-wrap gap-3">
            <Button type="submit" variant="secondary" loading={act.isPending}>
              Dismiss it
            </Button>
            <Button variant="tertiary" onClick={() => setDismissing(false)}>
              Back
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap gap-3">
          {report.kind === "parent_absent" && !report.responded_at && (
            <Button variant="secondary" fullWidthOnPhone={false} loading={act.isPending} onClick={() => act.mutate({ path: "answered" })}>
              The parent answered
            </Button>
          )}
          <Button fullWidthOnPhone={false} loading={act.isPending} onClick={() => act.mutate({ path: "confirm" })}>
            Confirm
          </Button>
          <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setDismissing(true)}>
            Dismiss
          </Button>
        </div>
      )}
      {error && !dismissing && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </li>
  );
}

export function ReportsPage() {
  const reports = useQuery({
    queryKey: REPORTS_KEY,
    queryFn: () => apiFetch<AdminReport[]>("/admin/reports"),
    refetchInterval: 30_000, // the 20-minute waits move on
  });
  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-4">
      <BackLink to="/admin" label="Admin" />
      <h1>Reports</h1>
      {reports.isPending && <p className="text-muted">Loading…</p>}
      {reports.isError && (
        <p role="alert" className="text-danger">
          {errorMessage(reports.error)}
        </p>
      )}
      {reports.isSuccess &&
        (reports.data.length === 0 ? (
          <EmptyState message="No reports waiting." />
        ) : (
          <Card as="section" padding="roomy" aria-label="Open reports">
            <ul>
              {reports.data.map((report) => (
                <ReportItem key={report.id} report={report} />
              ))}
            </ul>
          </Card>
        ))}
    </section>
  );
}
