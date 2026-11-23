import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { BackLink, Button, Card, Checkbox, Select, TextInput, Textarea } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import { apiFetch } from "../../lib/api";
import { formatDay } from "../../lib/format";
import { FROM_PACIFYCO, FROM_THEM, TYPE_WORDS, when } from "../HelpPages";
import { ViewDocumentButton, errorMessage, type DocumentSummary } from "./shared";

// Complaints, appeals and the Grievance Officer, for admins (CLAUDE.md 6.12; phase 10). The queue shows the
// time left on each target; one complaint's page holds the conversation and what can be done with it: reply,
// mark a serious safety matter (15 days), resolve, decide an appeal (never by the admin who made the
// decision), and, for the Grievance Officer, acknowledge and decide escalated ones. Public holidays (for the
// appeal's 7 working days) are on their own page.

export type AdminComplaintRow = {
  id: string;
  type: string;
  topic: string | null;
  status: string;
  person_name: string | null;
  person_role: "parent" | "sitter";
  created_at: string;
  reply_by: string;
  resolve_by: string;
  first_reply_at: string | null;
  escalated_at: string | null;
  officer_acknowledged_at: string | null;
  late: boolean;
  serious: boolean;
  overdue: boolean;
};

export type AdminComplaint = AdminComplaintRow & {
  description: string;
  happened_on: string | null;
  person: {
    id: string;
    full_name: string | null;
    role: "parent" | "sitter";
    email: string;
    phone: string | null;
    status: string;
  };
  booking_id: string | null;
  booking_starts_at: string | null;
  resolution: string | null;
  resolved_at: string | null;
  appeal_outcome: "upheld" | "rejected" | null;
  decision: {
    action: string;
    kind: string | null;
    reason: string;
    at: string;
    by: string | null;
    by_id: string | null;
  } | null;
  escalation_note: string | null;
  escalated_by_person: boolean;
  acknowledge_by: string | null;
  decide_by: string | null;
  officer_decision: string | null;
  officer_decided_at: string | null;
  messages: { id: string; from_pacifyco: boolean; by: string | null; body: string; at: string }[];
  attachments: DocumentSummary[];
  cannot_handle: string | null;
  is_officer: boolean;
};

const VIEWS = {
  open: "Open complaints",
  appeals: "Appeals",
  escalated: "With the Grievance Officer",
  done: "Resolved and closed",
};

const STATUS = {
  open: "Waiting for a first reply",
  replied: "Replied",
  resolved: "Resolved",
  escalated: "With the Grievance Officer",
  appealed: "Appealed",
  closed: "Closed by the Grievance Officer",
} as Record<string, string>;

const TOPICS: Record<string, string> = { running_late: "Running late", other: "Something else" };

/** How long until a moment, or how long ago it passed: "5 h left", "2 days overdue". */
export function timeLeft(iso: string, now: Date): string {
  const minutes = Math.round((new Date(iso).getTime() - now.getTime()) / 60_000);
  const size = Math.abs(minutes);
  const amount =
    size < 60 ? `${size} min` : size < 48 * 60 ? `${Math.round(size / 60)} h` : `${Math.round(size / 1440)} days`;
  return minutes >= 0 ? `${amount} left` : `${amount} overdue`;
}

/** The target that matters now, in words. */
export function nextTarget(row: AdminComplaintRow, now: Date): string | null {
  if (row.status === "escalated" && row.escalated_at) {
    const escalated = new Date(row.escalated_at).getTime();
    if (!row.officer_acknowledged_at) {
      return `Acknowledge: ${timeLeft(new Date(escalated + 24 * 3_600_000).toISOString(), now)}`;
    }
    return `Decide: ${timeLeft(new Date(escalated + 15 * 86_400_000).toISOString(), now)}`;
  }
  if (row.status !== "open" && row.status !== "replied") return null;
  if (!row.first_reply_at) return `First reply: ${timeLeft(row.reply_by, now)}`;
  return `${row.type === "suspension" ? "Decide" : "Resolve"}: ${timeLeft(row.resolve_by, now)}`;
}

function complaintTitle(row: { type: string; topic: string | null }): string {
  const what = TYPE_WORDS[row.type] ?? "A complaint";
  return row.topic ? `${what}: ${(TOPICS[row.topic] ?? row.topic).toLowerCase()}` : what;
}

export function ComplaintsPage() {
  const [params, setParams] = useSearchParams();
  const view = (params.get("view") ?? "open") as keyof typeof VIEWS;
  const list = useQuery({
    queryKey: ["admin", "complaints", view],
    queryFn: () => apiFetch<AdminComplaintRow[]>(`/admin/complaints?view=${view}`),
    refetchInterval: 60_000,
  });
  const now = new Date();
  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-6">
      <BackLink to="/admin" label="Admin" />
      <h1>Complaints</h1>
      <p className="text-muted">
        Reply within 24 hours and resolve within 48 (15 days for a serious safety matter). Complaints still open at
        their target go to the Grievance Officer. Appeals are decided within 7 working days, by an admin who didn't
        make the decision. <Link to="/admin/holidays">Public holidays</Link>
      </p>
      <Select
        label="Show"
        value={view}
        onChange={(event) => setParams({ view: event.target.value }, { replace: true })}
      >
        {(Object.keys(VIEWS) as (keyof typeof VIEWS)[]).map((item) => (
          <option key={item} value={item}>
            {VIEWS[item]}
          </option>
        ))}
      </Select>
      {list.isPending && <p className="text-center text-muted">Loading…</p>}
      {list.isError && (
        <p role="alert" className="text-center text-danger">
          {errorMessage(list.error)}
        </p>
      )}
      {list.isSuccess &&
        (list.data.length === 0 ? (
          <p className="text-center text-muted">Nothing here.</p>
        ) : (
          <Card padding="roomy">
            <ul aria-label={VIEWS[view]}>
              {list.data.map((row) => {
                const target = nextTarget(row, now);
                return (
                  <li key={row.id} className="border-t border-line first:border-t-0">
                    <Link
                      to={`/admin/complaints/${row.id}`}
                      className="flex items-center gap-4 py-4 text-ink no-underline"
                    >
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span className="text-ui">
                          {complaintTitle(row)} · {row.person_name ?? "No name yet"} ({row.person_role})
                        </span>
                        <span className="text-small text-muted">
                          {STATUS[row.status]} · Raised {formatDay(new Date(row.created_at))}
                          {row.late && " · Late"}
                          {row.serious && " · Serious safety matter"}
                        </span>
                        {target && (
                          <span className={cx("text-small", row.overdue ? "text-danger" : "text-muted")}>{target}</span>
                        )}
                      </span>
                      <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-muted" />
                    </Link>
                  </li>
                );
              })}
            </ul>
          </Card>
        ))}
    </section>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = `${title.toLowerCase().replace(/[^a-z]+/g, "-")}-heading`;
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3" aria-labelledby={id}>
      <h2 id={id} className="text-h3">
        {title}
      </h2>
      {children}
    </Card>
  );
}

function useAct(complaintId: string, path: string, onDone?: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body?: Record<string, unknown>) =>
      apiFetch<AdminComplaint>(`/admin/complaints/${complaintId}/${path}`, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["admin", "complaint", complaintId], updated);
      void queryClient.invalidateQueries({ queryKey: ["admin", "complaints"] });
      onDone?.();
    },
  });
}

/** A textarea and a button; the text is required. */
function TextAction({
  complaintId,
  path,
  label,
  hint,
  button,
  field = "body",
  extra,
  children,
}: {
  complaintId: string;
  path: string;
  label: string;
  hint?: string;
  button: string;
  field?: string;
  extra?: () => Record<string, unknown> | string;
  children?: ReactNode;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const act = useAct(complaintId, path, () => setText(""));
  function submit(event: FormEvent) {
    event.preventDefault();
    const more = extra?.() ?? {};
    if (typeof more === "string") return setError(more);
    if (!text.trim()) return setError("Please write something first.");
    setError(null);
    act.mutate({ ...more, [field]: text.trim() }, { onError: (failed) => setError(errorMessage(failed)) });
  }
  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-3">
      {children}
      <Textarea label={label} hint={hint} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} />
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
      <div>
        <Button type="submit" variant="secondary" loading={act.isPending} fullWidthOnPhone={false}>
          {button}
        </Button>
      </div>
    </form>
  );
}

function AppealForm({ complaintId }: { complaintId: string }) {
  const [outcome, setOutcome] = useState<"" | "upheld" | "rejected">("");
  const [reinstate, setReinstate] = useState(false);
  return (
    <TextAction
      complaintId={complaintId}
      path="appeal"
      field="note"
      label="The reasons for the decision"
      hint="They're emailed and shown to the person."
      button="Decide the appeal"
      extra={() => (outcome ? { outcome, reinstate: outcome === "upheld" && reinstate } : "Choose upheld or rejected.")}
    >
      <fieldset className="flex flex-col gap-2">
        <legend className="text-ui text-ink">Outcome</legend>
        {(
          [
            ["upheld", "Upheld: the decision is overturned"],
            ["rejected", "Rejected: the decision stands"],
          ] as const
        ).map(([value, label]) => (
          <label key={value} className="flex items-center gap-2 text-ink">
            <input
              type="radio"
              name="appeal-outcome"
              value={value}
              checked={outcome === value}
              onChange={() => setOutcome(value)}
            />
            {label}
          </label>
        ))}
      </fieldset>
      {outcome === "upheld" && (
        <Checkbox
          label="Reinstate the account now (otherwise reinstate it by hand later, from their page)"
          checked={reinstate}
          onChange={(event) => setReinstate(event.target.checked)}
        />
      )}
    </TextAction>
  );
}

function SeriousToggle({ complaint }: { complaint: AdminComplaint }) {
  const act = useAct(complaint.id, "serious");
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-2">
      <p className="text-muted">
        {complaint.serious
          ? "Marked a serious safety matter: up to 15 days to resolve. Keep the person updated."
          : "A serious safety matter can take up to 15 days to resolve, with updates."}
      </p>
      <div>
        <Button
          variant="tertiary"
          fullWidthOnPhone={false}
          loading={act.isPending}
          onClick={() =>
            act.mutate({ serious: !complaint.serious }, { onError: (failed) => setError(errorMessage(failed)) })
          }
        >
          {complaint.serious ? "Not a serious safety matter" : "Mark a serious safety matter"}
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export function AdminComplaintPage() {
  const { complaintId = "" } = useParams();
  const complaint = useQuery({
    queryKey: ["admin", "complaint", complaintId],
    queryFn: () => apiFetch<AdminComplaint>(`/admin/complaints/${complaintId}`),
  });
  const acknowledge = useAct(complaintId, "acknowledge");
  if (complaint.isPending) return <p className="text-center text-muted">Loading…</p>;
  if (complaint.isError) {
    return (
      <p role="alert" className="text-center text-danger">
        {errorMessage(complaint.error)}
      </p>
    );
  }
  const data = complaint.data;
  const now = new Date();
  const target = nextTarget(data, now);
  const active = data.status === "open" || data.status === "replied";
  const canAct = data.cannot_handle === null;
  const personPath = `/admin/${data.person.role === "sitter" ? "sitters" : "parents"}/${data.person.id}`;

  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-6">
      <BackLink to="/admin/complaints" label="Complaints" />
      <h1>{complaintTitle(data)}</h1>
      <p className={cx("text-ui", data.overdue ? "text-danger" : "text-muted")}>
        {STATUS[data.status]}
        {target && ` · ${target}`}
      </p>
      {data.cannot_handle && (
        <p role="status" className="rounded-md bg-surface-sunken p-4 text-ink">
          {data.cannot_handle}
        </p>
      )}

      <Section title="The complaint">
        <p className="text-small text-muted">
          From <Link to={personPath}>{data.person.full_name ?? "No name yet"}</Link> ({data.person.role}
          {data.person.status !== "active" && `, ${data.person.status}`}) · {data.person.email}
          {data.person.phone && ` · ${data.person.phone}`}
        </p>
        <p className="text-small text-muted">
          Raised {when(data.created_at)}
          {data.happened_on && ` · Happened on ${formatDay(new Date(`${data.happened_on}T12:00:00+05:30`))}`}
          {data.late && " · Raised more than 24 hours after it happened"}
          {data.serious && " · Serious safety matter"}
        </p>
        {data.booking_id && (
          <p className="text-small">
            <Link to={`/admin/bookings/${data.booking_id}`}>
              The booking{data.booking_starts_at && ` on ${when(data.booking_starts_at)}`}
            </Link>
          </p>
        )}
        <p className="whitespace-pre-line text-ink">{data.description}</p>
        {data.attachments.length > 0 && (
          <div className="flex flex-wrap gap-3">
            {data.attachments.map((file, index) => (
              <ViewDocumentButton key={file.id} document={file} label={`File ${index + 1}`} />
            ))}
          </div>
        )}
      </Section>

      {data.decision && (
        <Section title="The decision appealed">
          <p className="text-small text-muted">
            {data.decision.action === "removed" ? "Removed" : "Suspended"} {when(data.decision.at)} by{" "}
            {data.decision.by ?? "the rules (automatic)"}
            {data.decision.kind && ` · ${data.decision.kind.replaceAll("_", " ")}`}
          </p>
          <p className="whitespace-pre-line text-ink">{data.decision.reason}</p>
        </Section>
      )}

      <Section title="Messages">
        {data.messages.length === 0 && <p className="text-muted">No messages yet. The first one is the first reply.</p>}
        <ul className="flex flex-col gap-3">
          {data.messages.map((message) => (
            <li
              key={message.id}
              className={message.from_pacifyco ? FROM_PACIFYCO : FROM_THEM}
            >
              <p className="text-small text-muted">
                {message.from_pacifyco
                  ? `${message.by ?? "An admin"} (Pacifyco)`
                  : (data.person.full_name ?? "They")}{" "}
                ·{" "}
                {when(message.at)}
              </p>
              <p className="whitespace-pre-line text-ink">{message.body}</p>
            </li>
          ))}
        </ul>
        {canAct && (
          <TextAction
            complaintId={data.id}
            path="messages"
            label="Write to them"
            hint="They're emailed it and see it in the app."
            button="Send"
          />
        )}
      </Section>

      {canAct && active && data.type !== "suspension" && (
        <Section title="Resolve">
          <SeriousToggle complaint={data} />
          <TextAction
            complaintId={data.id}
            path="resolve"
            label="What was done"
            hint="They're emailed it. If they disagree, they can send it to the Grievance Officer."
            button="Resolve the complaint"
          />
        </Section>
      )}

      {canAct && active && data.type === "suspension" && (
        <Section title="Decide the appeal">
          <AppealForm complaintId={data.id} />
        </Section>
      )}

      {(data.resolution || data.appeal_outcome) && (
        <Section title={data.type === "suspension" ? "The appeal decision" : "Resolved"}>
          {data.appeal_outcome && (
            <p className="text-ink">{data.appeal_outcome === "upheld" ? "Upheld" : "Rejected"}</p>
          )}
          {data.resolved_at && <p className="text-small text-muted">{when(data.resolved_at)}</p>}
          {data.resolution && <p className="whitespace-pre-line text-ink">{data.resolution}</p>}
        </Section>
      )}

      {(data.status === "escalated" || data.officer_decision) && (
        <Section title="The Grievance Officer">
          <p className="text-small text-muted">
            {data.escalated_by_person ? "They disagreed with how it was resolved" : "It wasn't resolved in time"}
            {data.escalated_at && ` · Escalated ${when(data.escalated_at)}`}
          </p>
          {data.escalation_note && <p className="whitespace-pre-line text-ink">{data.escalation_note}</p>}
          {data.status === "escalated" && data.acknowledge_by && data.decide_by && (
            <p className="text-small text-muted">
              {data.officer_acknowledged_at
                ? `Acknowledged ${when(data.officer_acknowledged_at)}`
                : `Acknowledge by ${when(data.acknowledge_by)}`}{" "}
              · Decide by {when(data.decide_by)}
            </p>
          )}
          {data.officer_decision && (
            <>
              <p className="text-small text-muted">
                Decided {data.officer_decided_at && when(data.officer_decided_at)}
              </p>
              <p className="whitespace-pre-line text-ink">{data.officer_decision}</p>
            </>
          )}
          {canAct && data.status === "escalated" && (
            <>
              {!data.officer_acknowledged_at && (
                <div>
                  <Button
                    variant="secondary"
                    fullWidthOnPhone={false}
                    loading={acknowledge.isPending}
                    onClick={() => acknowledge.mutate(undefined)}
                  >
                    Acknowledge it
                  </Button>
                </div>
              )}
              <TextAction
                complaintId={data.id}
                path="officer-decision"
                label="Your written decision, with reasons"
                hint="It's emailed to them and closes the complaint."
                button="Send the decision"
              />
            </>
          )}
        </Section>
      )}
    </section>
  );
}

type Holiday = { day: string; name: string };

export function HolidaysPage() {
  const queryClient = useQueryClient();
  const [day, setDay] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["admin", "holidays"], queryFn: () => apiFetch<Holiday[]>("/admin/holidays") });
  const saved = (updated: Holiday[]) => queryClient.setQueryData(["admin", "holidays"], updated);
  const add = useMutation({
    mutationFn: () => apiFetch<Holiday[]>("/admin/holidays", { method: "POST", body: JSON.stringify({ day, name }) }),
    onSuccess: (updated) => {
      saved(updated);
      setDay("");
      setName("");
      setError(null);
    },
    onError: (failed) => setError(errorMessage(failed)),
  });
  const remove = useMutation({
    mutationFn: (holiday: string) => apiFetch<Holiday[]>(`/admin/holidays/${holiday}`, { method: "DELETE" }),
    onSuccess: saved,
    onError: (failed) => setError(errorMessage(failed)),
  });
  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-6">
      <BackLink to="/admin/complaints" label="Complaints" />
      <h1>Public holidays</h1>
      <p className="text-muted">
        Appeals are reviewed within 7 working days: Monday to Friday, not counting the holidays here. A change counts
        for appeals made after it.
      </p>
      <Card padding="roomy">
        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (!day || !name.trim()) return setError("Choose the day and give it a name.");
            add.mutate();
          }}
          className="flex flex-col gap-4"
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <TextInput label="Day" type="date" value={day} onChange={(event) => setDay(event.target.value)} />
            <TextInput label="Name" maxLength={100} value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          {error && (
            <p role="alert" className="text-small text-danger">
              {error}
            </p>
          )}
          <div>
            <Button type="submit" variant="secondary" loading={add.isPending} fullWidthOnPhone={false}>
              Add the holiday
            </Button>
          </div>
        </form>
      </Card>
      {list.isSuccess &&
        (list.data.length === 0 ? (
          <p className="text-center text-muted">No public holidays added yet.</p>
        ) : (
          <Card padding="roomy">
            <ul aria-label="Public holidays">
              {list.data.map((holiday) => (
                <li
                  key={holiday.day}
                  className="flex items-center justify-between gap-3 border-t border-line py-3 first:border-t-0"
                >
                  <span className="text-ink">
                    {formatDay(new Date(`${holiday.day}T12:00:00+05:30`))} {holiday.day.slice(0, 4)} · {holiday.name}
                  </span>
                  <Button
                    variant="tertiary"
                    fullWidthOnPhone={false}
                    loading={remove.isPending && remove.variables === holiday.day}
                    onClick={() => remove.mutate(holiday.day)}
                    aria-label={`Remove ${holiday.name}`}
                  >
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          </Card>
        ))}
    </section>
  );
}
