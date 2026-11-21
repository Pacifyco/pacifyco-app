import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BackLink, Button, Card, EmptyState, showToast } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDay, formatMobile, formatTime } from "../../lib/format";
import { errorMessage } from "./shared";

// Issues (CLAUDE.md 6.9): non-emergency problems raised from a booking, kept as complaints linked to it. Get in
// touch, mark it replied, then resolved. (Reply and resolve targets, escalation and appeals come with the
// complaints process, 6.12.)

export type AdminIssue = {
  id: string;
  topic: "running_late" | "other" | null;
  description: string;
  status: "open" | "replied";
  raised_by: "parent" | "sitter";
  created_at: string;
  booking_id: string | null;
  starts_at: string | null;
  parent_name: string | null;
  parent_phone: string | null;
  sitter_name: string | null;
  sitter_phone: string | null;
};

const ISSUES_KEY = ["admin", "issues"];

const TOPIC_WORDS: Record<string, string> = { running_late: "Running late", other: "Something else" };

function when(iso: string): string {
  const moment = new Date(iso);
  return `${formatDay(moment)}, ${formatTime(moment)}`;
}

function IssueItem({ issue }: { issue: AdminIssue }) {
  const queryClient = useQueryClient();
  const act = useMutation({
    mutationFn: (path: "replied" | "resolved") =>
      apiFetch<AdminIssue>(`/admin/issues/${issue.id}/${path}`, { method: "POST" }),
    onSuccess: async (_, path) => {
      showToast(path === "replied" ? "Marked replied" : "Resolved");
      await queryClient.invalidateQueries({ queryKey: ISSUES_KEY });
    },
  });
  const raiser = issue.raised_by === "parent" ? [issue.parent_name, issue.parent_phone] : [issue.sitter_name, issue.sitter_phone];
  return (
    <li className="flex flex-col gap-3 border-t border-line py-5 first:border-t-0">
      <p className="text-eyebrow text-muted uppercase">
        {TOPIC_WORDS[issue.topic ?? "other"]} · from the {issue.raised_by} · {issue.status}
      </p>
      <p className="text-ink">{issue.description}</p>
      <p className="text-small text-muted">
        Raised {when(issue.created_at)}
        {issue.starts_at ? ` · booking ${when(issue.starts_at)}` : ""}
      </p>
      <p className="text-small text-ink">
        {raiser[0] ?? "Not given"}
        {raiser[1] && (
          <>
            {" · "}
            <a href={`tel:${raiser[1]}`}>{formatMobile(raiser[1])}</a>
          </>
        )}
      </p>
      <div className="flex flex-wrap gap-3">
        {issue.status === "open" && (
          <Button variant="secondary" fullWidthOnPhone={false} loading={act.isPending} onClick={() => act.mutate("replied")}>
            Mark replied
          </Button>
        )}
        <Button fullWidthOnPhone={false} loading={act.isPending} onClick={() => act.mutate("resolved")}>
          Resolved
        </Button>
      </div>
      {act.isError && (
        <p role="alert" className="text-small text-danger">
          {errorMessage(act.error)}
        </p>
      )}
    </li>
  );
}

export function IssuesPage() {
  const issues = useQuery({ queryKey: ISSUES_KEY, queryFn: () => apiFetch<AdminIssue[]>("/admin/issues") });
  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-4">
      <BackLink to="/admin" label="Admin" />
      <h1>Issues</h1>
      {issues.isPending && <p className="text-muted">Loading…</p>}
      {issues.isError && (
        <p role="alert" className="text-danger">
          {errorMessage(issues.error)}
        </p>
      )}
      {issues.isSuccess &&
        (issues.data.length === 0 ? (
          <EmptyState message="No issues open." />
        ) : (
          <Card as="section" padding="roomy" aria-label="Open issues">
            <ul>
              {issues.data.map((issue) => (
                <IssueItem key={issue.id} issue={issue} />
              ))}
            </ul>
          </Card>
        ))}
    </section>
  );
}
