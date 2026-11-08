import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CircleCheck, CircleX, Clock } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { Button, Textarea } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import { ApiError, apiFetch } from "../../lib/api";

// Pieces shared by the admin verification pages (CLAUDE.md 7).

export type ReviewStatus = "pending" | "approved" | "rejected";

export type DocumentSummary = { id: string; type: string; uploaded_at: string };

export const DOCUMENT_LABELS: Record<string, string> = {
  government_id: "Government ID",
  college_or_work_id: "College or work ID",
  police_certificate: "Police clearance certificate",
  first_aid_certificate: "First-aid certificate",
  birth_certificate: "Birth certificate",
  photo: "Photo",
  doctor_note: "Doctor's note",
};

const STATUS_WORDS: Record<ReviewStatus, string> = { pending: "Waiting", approved: "Approved", rejected: "Rejected" };

// design.md 12: status is trust or danger with words; "waiting" is muted text on a sunken surface.
export function StatusPill({ status }: { status: ReviewStatus }) {
  const Icon = status === "approved" ? CircleCheck : status === "rejected" ? CircleX : Clock;
  return (
    <span
      className={cx(
        "inline-flex shrink-0 items-center gap-1 rounded-pill bg-surface-sunken py-1 pr-3 pl-2 text-small",
        status === "approved" ? "text-trust" : status === "rejected" ? "text-danger" : "text-muted",
      )}
    >
      <Icon aria-hidden="true" size={18} strokeWidth={1.75} />
      {STATUS_WORDS[status]}
    </span>
  );
}

export function BackToQueue() {
  return (
    <Link to="/admin/verifications" className="inline-flex items-center gap-2 text-small">
      <ArrowLeft aria-hidden="true" size={18} strokeWidth={1.75} />
      Verification queue
    </Link>
  );
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}

// Opens the document in a new tab through a short-lived signed URL. Every view is logged by the API.
// The tab is opened before the request so pop-up blockers allow it.
export function ViewDocumentButton({ document, label }: { document: DocumentSummary; label?: string }) {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const name = label ?? DOCUMENT_LABELS[document.type] ?? document.type;

  async function view() {
    setError(null);
    setLoading(true);
    const tab = window.open("", "_blank");
    try {
      const { url } = await apiFetch<{ url: string }>(`/admin/documents/${document.id}/view-url`);
      if (tab) {
        tab.opener = null;
        tab.location.href = url;
      }
    } catch (caught) {
      tab?.close();
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  return (
    <span className="inline-flex flex-col gap-1">
      <Button variant="secondary" fullWidthOnPhone={false} loading={loading} onClick={() => void view()}>
        View {name.toLowerCase()}
      </Button>
      {error && (
        <span role="alert" className="text-small text-danger">
          {error}
        </span>
      )}
    </span>
  );
}

type BodyFor = (approved: boolean, notes: string | null) => unknown;

const defaultBody: BodyFor = (approved, notes) => ({ approved, notes });

export function useDecision(path: string, invalidate: unknown[][], body: BodyFor = defaultBody) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ approved, notes }: { approved: boolean; notes: string | null }) =>
      apiFetch<unknown>(path, { method: "POST", body: JSON.stringify(body(approved, notes)) }),
    onSuccess: () => Promise.all(invalidate.map((queryKey) => queryClient.invalidateQueries({ queryKey }))),
  });
}

// Notes plus Approve and Reject. Notes are optional but recorded with the decision (audit logged).
export function DecisionForm({
  path,
  invalidate,
  subject,
  approveLabel = "Approve",
  rejectLabel = "Reject",
  body,
}: {
  path: string;
  invalidate: unknown[][];
  subject: string;
  approveLabel?: string;
  rejectLabel?: string;
  /** The request body, when the endpoint doesn't take {approved, notes}. */
  body?: BodyFor;
}) {
  const [notes, setNotes] = useState("");
  const decision = useDecision(path, invalidate, body);
  const decide = (approved: boolean) => decision.mutate({ approved, notes: notes.trim() || null });

  return (
    <div className="mt-4 flex flex-col gap-3">
      <Textarea
        label={`Notes on ${subject}`}
        optional
        rows={2}
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
      />
      <div className="flex flex-wrap gap-3">
        <Button fullWidthOnPhone={false} loading={decision.isPending} onClick={() => decide(true)}>
          {approveLabel}
        </Button>
        <Button variant="secondary" fullWidthOnPhone={false} disabled={decision.isPending} onClick={() => decide(false)}>
          {rejectLabel}
        </Button>
      </div>
      {decision.isError && (
        <p role="alert" className="text-small text-danger">
          {errorMessage(decision.error)}
        </p>
      )}
    </div>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 sm:flex-row sm:gap-4">
      <dt className="text-small text-muted sm:w-40 sm:shrink-0">{label}</dt>
      <dd className="text-body text-ink">{children}</dd>
    </div>
  );
}
