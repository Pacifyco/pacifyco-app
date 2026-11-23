import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { clientCheck } from "../components/documents/DocumentUpload";
import {
  BackLink,
  Button,
  ButtonLink,
  Card,
  EmptyState,
  Select,
  TextInput,
  Textarea,
  showToast,
} from "../components/ui";
import { config } from "../config";
import { ApiError, apiFetch } from "../lib/api";
import { formatDay, formatTime } from "../lib/format";

// Help and complaints for parents and sitters (CLAUDE.md 6.12; phase 10). Raise a complaint (up to 3 files),
// read Pacifyco's replies and answer them, and send it to the Grievance Officer if they disagree with how it
// was resolved. Parent pages have no subheadings (CLAUDE.md 7), so nor do these.

type Role = "parent" | "sitter";

export type ComplaintMessage = { id: string; from_pacifyco: boolean; body: string; at: string };

export type ComplaintRow = { id: string; type: string; status: string; description: string; created_at: string };

export type Complaint = ComplaintRow & {
  request_kind: string | null;
  booking_id: string | null;
  happened_on: string | null;
  late: boolean;
  reply_by: string;
  resolve_by: string;
  first_reply_at: string | null;
  resolved_at: string | null;
  resolution: string | null;
  appeal_outcome: "upheld" | "rejected" | null;
  escalated_at: string | null;
  officer_acknowledged_at: string | null;
  officer_decision: string | null;
  officer_decided_at: string | null;
  can_write: boolean;
  can_escalate: boolean;
  can_attach: boolean;
  messages: ComplaintMessage[];
  attachments: { id: string; uploaded_at: string }[];
};

const TYPES: Record<Role, [string, string][]> = {
  parent: [
    ["payment", "A payment"],
    ["sitter", "A sitter"],
    ["review", "A review"],
    ["data_request", "Your data"],
    ["other", "Something else"],
  ],
  sitter: [
    ["payment", "A payment or my pay"],
    ["family", "A family"],
    ["review", "A review"],
    ["data_request", "Your data"],
    ["other", "Something else"],
  ],
};

export const TYPE_WORDS: Record<string, string> = {
  booking: "A booking",
  payment: "A payment",
  family: "A family",
  sitter: "A sitter",
  review: "A review",
  suspension: "An appeal",
  data_request: "Your data",
  other: "Something else",
};

export const STATUS_WORDS: Record<string, string> = {
  open: "Waiting for our reply",
  replied: "We've replied",
  resolved: "Resolved",
  escalated: "With our Grievance Officer",
  closed: "Decided by our Grievance Officer",
};

const MAX_FILES = 3;

// A data request (CLAUDE.md 6.13): what they'd like. An admin handles it by hand.
export const REQUEST_WORDS: Record<string, string> = {
  access: "A copy of the data we hold about you",
  correction: "To correct something we hold about you",
  deletion: "To delete your data",
};
export const FROM_PACIFYCO = "rounded-md bg-surface-sunken p-4";
export const FROM_THEM = "rounded-md border border-line p-4";

export function when(iso: string): string {
  const moment = new Date(iso);
  return `${formatDay(moment)}, ${formatTime(moment)}`;
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "That didn't go through. Please try again.";
}

/** Upload one file to a complaint: a signed upload, then the API checks it. */
async function attach(complaintId: string, file: File): Promise<void> {
  const ticket = await apiFetch<{ document_id: string; upload_url: string }>("/documents/upload-url", {
    method: "POST",
    body: JSON.stringify({ type: "complaint_attachment", complaint_id: complaintId }),
  });
  const put = await fetch(ticket.upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type } });
  if (!put.ok) throw new ApiError(put.status, "upload_failed", "That upload didn't go through. Please try again.");
  const confirmed = await apiFetch<{ status: string }>(`/documents/${ticket.document_id}/confirm`, { method: "POST" });
  if (confirmed.status !== "uploaded") {
    throw new ApiError(422, "invalid_file", "Please upload a PDF, JPG or PNG of at most 5 MB.");
  }
}

function checkFiles(files: File[]): string | undefined {
  if (files.length > MAX_FILES) return `Please choose up to ${MAX_FILES} files.`;
  return files.map((file) => clientCheck(file, "complaint_attachment")).find(Boolean);
}

/** The Grievance Officer's details, when they're set (config, CLAUDE.md 6.12). */
export function GrievanceOfficer() {
  const { grievanceName, grievanceEmail, grievancePhone } = config.legal;
  if (!grievanceName && !grievanceEmail) return null;
  return (
    <p className="text-muted">
      If you're not happy with how we've handled a complaint, it goes to our Grievance Officer
      {grievanceName ? `, ${grievanceName}` : ""}
      {grievanceEmail && (
        <>
          {" "}
          (<a href={`mailto:${grievanceEmail}`}>{grievanceEmail}</a>
          {grievancePhone && (
            <>
              , <a href={`tel:${grievancePhone.replace(/\s/g, "")}`}>{grievancePhone}</a>
            </>
          )}
          )
        </>
      )}
      .
    </p>
  );
}

export function HelpPage({ role }: { role: Role }) {
  const list = useQuery({
    queryKey: ["complaints"],
    queryFn: () => apiFetch<ComplaintRow[]>("/me/complaints"),
  });
  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-6">
      <h1>Help</h1>
      <p className="text-muted">
        If something's gone wrong, tell us. We'll reply within 24 hours and aim to sort it out within 48 hours.
        Please tell us within 24 hours of it happening if you can, though later is fine too.
      </p>
      <div>
        <ButtonLink to={`/${role}/help/new`} fullWidthOnPhone={false}>
          Raise a complaint
        </ButtonLink>
      </div>
      {list.isError && (
        <p role="alert" className="text-danger">
          {errorText(list.error)}
        </p>
      )}
      {list.isSuccess &&
        (list.data.length === 0 ? (
          <EmptyState message="You haven't raised a complaint." />
        ) : (
          <Card padding="roomy">
            <ul aria-label="Your complaints">
              {list.data.map((item) => (
                <li key={item.id} className="border-t border-line first:border-t-0">
                  <Link to={`/${role}/help/${item.id}`} className="flex items-center gap-4 py-4 text-ink no-underline">
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="text-ui">
                        {TYPE_WORDS[item.type] ?? "A complaint"} · {formatDay(new Date(item.created_at))}
                      </span>
                      <span className="truncate text-small text-muted">{STATUS_WORDS[item.status]}</span>
                    </span>
                    <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-muted" />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      <p className="text-muted">
        You can also reach us at <a href="mailto:founders@pacifyco.in">founders@pacifyco.in</a> or{" "}
        <a href="tel:+918848873841">+91 8848873841</a>. In an emergency during a booking, use the Emergency button on
        the booking, and if anyone is in danger, call 112.
      </p>
      <GrievanceOfficer />
    </section>
  );
}

export function NewComplaintPage({ role }: { role: Role }) {
  const [params] = useSearchParams();
  const bookingId = params.get("booking");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const asked = params.get("data");
  const [type, setType] = useState(bookingId ? "booking" : asked ? "data_request" : "");
  const [requestKind, setRequestKind] = useState(asked && asked in REQUEST_WORDS ? asked : "");
  const [happenedOn, setHappenedOn] = useState("");
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const send = useMutation({
    mutationFn: async () => {
      const made = await apiFetch<Complaint>("/me/complaints", {
        method: "POST",
        body: JSON.stringify({
          type,
          description: description.trim(),
          booking_id: bookingId,
          happened_on: bookingId || !happenedOn || type === "data_request" ? null : happenedOn,
          request_kind: type === "data_request" ? requestKind : null,
        }),
      });
      let failed = false;
      for (const file of files) {
        try {
          await attach(made.id, file);
        } catch {
          failed = true;
        }
      }
      return { made, failed };
    },
    onSuccess: ({ made, failed }) => {
      void queryClient.invalidateQueries({ queryKey: ["complaints"] });
      showToast(failed ? "Complaint sent, but a file didn't upload. You can add it again." : "Complaint sent.");
      navigate(`/${role}/help/${made.id}`);
    },
    onError: (error) => setErrors({ form: errorText(error) }),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!type) found.type = "Please choose what it's about.";
    if (type === "data_request" && !requestKind) found.requestKind = "Please choose what you'd like.";
    if (!description.trim()) found.description = "Please tell us what happened.";
    const fileError = checkFiles(files);
    if (fileError) found.files = fileError;
    setErrors(found);
    if (Object.keys(found).length === 0) send.mutate();
  }

  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-6">
      <BackLink to={`/${role}/help`} label="Help" />
      <h1>Raise a complaint</h1>
      <Card padding="roomy">
        <form noValidate onSubmit={submit} className="flex flex-col gap-5">
          {bookingId ? (
            <p className="text-ink">About the booking you came from.</p>
          ) : (
            <>
              <Select
                label="What's it about?"
                value={type}
                error={errors.type}
                onChange={(event) => setType(event.target.value)}
              >
                <option value="">Choose one</option>
                {TYPES[role].map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
              {type === "data_request" ? (
                <Select
                  label="What would you like?"
                  value={requestKind}
                  error={errors.requestKind}
                  onChange={(event) => setRequestKind(event.target.value)}
                >
                  <option value="">Choose one</option>
                  {Object.entries(REQUEST_WORDS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </Select>
              ) : (
                <TextInput
                  label="When did it happen?"
                  type="date"
                  optional
                  value={happenedOn}
                  onChange={(event) => setHappenedOn(event.target.value)}
                />
              )}
            </>
          )}
          <Textarea
            label={type === "data_request" ? "Tell us more" : "What happened?"}
            rows={6}
            maxLength={2000}
            value={description}
            error={errors.description}
            onChange={(event) => setDescription(event.target.value)}
          />
          <FilePicker files={files} setFiles={setFiles} error={errors.files} />
          {errors.form && (
            <p role="alert" className="text-small text-danger">
              {errors.form}
            </p>
          )}
          <div>
            <Button type="submit" loading={send.isPending} fullWidthOnPhone={false}>
              Send my complaint
            </Button>
          </div>
        </form>
      </Card>
    </section>
  );
}

function FilePicker({
  files,
  setFiles,
  error,
  max = MAX_FILES,
}: {
  files: File[];
  setFiles: (files: File[]) => void;
  error?: string;
  max?: number;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor="complaint-files" className="text-ui text-ink">
        Files <span className="text-muted">(optional)</span>
      </label>
      <p id="complaint-files-hint" className="text-small text-muted">
        Up to {max} photos or documents: PDF, JPG or PNG, 5 MB each.
      </p>
      <input
        id="complaint-files"
        type="file"
        multiple
        accept="application/pdf,image/jpeg,image/png"
        aria-describedby="complaint-files-hint"
        onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
        className="text-small"
      />
      {files.length > 0 && <p className="text-small text-muted">{files.map((file) => file.name).join(", ")}</p>}
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/** The conversation on a complaint or appeal, with a reply box and, once resolved, sending it on. */
export function ComplaintThread({ complaint, refreshKey }: { complaint: Complaint; refreshKey: unknown[] }) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [why, setWhy] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [escalating, setEscalating] = useState(false);

  const done = () => void queryClient.invalidateQueries({ queryKey: refreshKey });
  const write = useMutation({
    mutationFn: () =>
      apiFetch<Complaint>(`/me/complaints/${complaint.id}/messages`, {
        method: "POST",
        body: JSON.stringify({ body: body.trim() }),
      }),
    onSuccess: () => {
      setBody("");
      setError(null);
      done();
    },
    onError: (failed) => setError(errorText(failed)),
  });
  const escalate = useMutation({
    mutationFn: () =>
      apiFetch<Complaint>(`/me/complaints/${complaint.id}/escalate`, {
        method: "POST",
        body: JSON.stringify({ body: why.trim() }),
      }),
    onSuccess: () => {
      setEscalating(false);
      showToast("Sent to our Grievance Officer.");
      done();
    },
    onError: (failed) => setError(errorText(failed)),
  });

  return (
    <div className="flex flex-col gap-4">
      {complaint.messages.length > 0 && (
        <ul aria-label="Messages" className="flex flex-col gap-3">
          {complaint.messages.map((message) => (
            <li
              key={message.id}
              className={message.from_pacifyco ? FROM_PACIFYCO : FROM_THEM}
            >
              <p className="text-small text-muted">
                {message.from_pacifyco ? "Pacifyco" : "You"} · {when(message.at)}
              </p>
              <p className="whitespace-pre-line text-ink">{message.body}</p>
            </li>
          ))}
        </ul>
      )}
      {complaint.can_write && (
        <form
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            if (!body.trim()) return setError("Please write a message.");
            write.mutate();
          }}
          className="flex flex-col gap-3"
        >
          <Textarea label="Write to us" maxLength={2000} value={body} onChange={(e) => setBody(e.target.value)} />
          <div>
            <Button type="submit" variant="secondary" loading={write.isPending} fullWidthOnPhone={false}>
              Send
            </Button>
          </div>
        </form>
      )}
      {complaint.can_escalate &&
        (escalating ? (
          <form
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              if (!why.trim()) return setError("Please tell us why you disagree.");
              escalate.mutate();
            }}
            className="flex flex-col gap-3"
          >
            <Textarea
              label="Why do you disagree?"
              hint={
                "Our Grievance Officer will acknowledge it within 24 hours and send a written decision within 15 days."
              }
              maxLength={2000}
              value={why}
              onChange={(e) => setWhy(e.target.value)}
            />
            <div className="flex flex-wrap gap-3">
              <Button type="submit" loading={escalate.isPending} fullWidthOnPhone={false}>
                Send to the Grievance Officer
              </Button>
              <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setEscalating(false)}>
                Not now
              </Button>
            </div>
          </form>
        ) : (
          <div>
            <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setEscalating(true)}>
              I disagree: send it to the Grievance Officer
            </Button>
          </div>
        ))}
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/** What's happened so far, in words. */
export function ComplaintState({ complaint }: { complaint: Complaint }) {
  if (complaint.status === "closed" && complaint.officer_decision) {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-ink">
          Our Grievance Officer's decision{complaint.officer_decided_at && `, ${when(complaint.officer_decided_at)}`}:
        </p>
        <p className="whitespace-pre-line text-ink">{complaint.officer_decision}</p>
      </div>
    );
  }
  if (complaint.status === "escalated") {
    return (
      <p className="text-ink">
        It's with our Grievance Officer, who'll{" "}
        {complaint.officer_acknowledged_at
          ? "send you a written decision"
          : "acknowledge it within 24 hours and send you a written decision"}{" "}
        within 15 days.
      </p>
    );
  }
  if (complaint.status === "resolved") {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-ink">
          {complaint.appeal_outcome === "upheld"
            ? "We've upheld your appeal."
            : complaint.appeal_outcome === "rejected"
              ? "We've looked at your appeal, and the decision stands."
              : "We've resolved this."}
        </p>
        {complaint.resolution && <p className="whitespace-pre-line text-ink">{complaint.resolution}</p>}
      </div>
    );
  }
  return (
    <p className="text-muted">
      {complaint.first_reply_at ? "" : `We'll reply by ${when(complaint.reply_by)}. `}
      We aim to sort it out by {when(complaint.resolve_by)}.
    </p>
  );
}

function AddFiles({ complaint }: { complaint: Complaint }) {
  const queryClient = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | undefined>();
  const room = MAX_FILES - complaint.attachments.length;
  const add = useMutation({
    mutationFn: async () => {
      for (const file of files) await attach(complaint.id, file);
    },
    onSuccess: () => {
      setFiles([]);
      showToast("Added.");
    },
    onError: (failed) => setError(errorText(failed)),
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ["complaint", complaint.id] }),
  });
  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        const found =
          files.length === 0
            ? "Please choose a file."
            : files.length > room
              ? `You can add ${room} more.`
              : checkFiles(files);
        setError(found);
        if (!found) add.mutate();
      }}
      className="flex flex-col gap-3"
    >
      <FilePicker files={files} setFiles={setFiles} error={error} max={room} />
      <div>
        <Button type="submit" variant="secondary" loading={add.isPending} fullWidthOnPhone={false}>
          Add files
        </Button>
      </div>
    </form>
  );
}

export function ComplaintPage({ role }: { role: Role }) {
  const { complaintId = "" } = useParams();
  const complaint = useQuery({
    queryKey: ["complaint", complaintId],
    queryFn: () => apiFetch<Complaint>(`/me/complaints/${complaintId}`),
  });
  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-6">
      <BackLink to={`/${role}/help`} label="Help" />
      {complaint.isPending && <p className="text-muted">Loading…</p>}
      {complaint.isError && (
        <p role="alert" className="text-danger">
          {errorText(complaint.error)}
        </p>
      )}
      {complaint.isSuccess && (
        <>
          <h1>{TYPE_WORDS[complaint.data.type] ?? "Your complaint"}</h1>
          <Card padding="roomy" className="flex flex-col gap-4">
            <p className="text-small text-muted">
              {STATUS_WORDS[complaint.data.status]} · Raised {when(complaint.data.created_at)}
              {complaint.data.attachments.length > 0 &&
                ` · ${complaint.data.attachments.length} file${complaint.data.attachments.length === 1 ? "" : "s"}`}
            </p>
            {complaint.data.request_kind && <p className="text-ink">{REQUEST_WORDS[complaint.data.request_kind]}</p>}
            <p className="whitespace-pre-line text-ink">{complaint.data.description}</p>
            <ComplaintState complaint={complaint.data} />
          </Card>
          <Card padding="roomy" className="flex flex-col gap-4">
            <ComplaintThread complaint={complaint.data} refreshKey={["complaint", complaintId]} />
          </Card>
          {complaint.data.can_attach && (
            <Card padding="roomy">
              <AddFiles complaint={complaint.data} />
            </Card>
          )}
        </>
      )}
    </section>
  );
}

type AppealState = {
  decision: { action: "suspended" | "removed"; reason: string; at: string } | null;
  appeal_by: string | null;
  can_appeal: boolean;
  appeal: Complaint | null;
};

/** On the "account on hold" page: the decision, and an appeal (within 15 days, CLAUDE.md 6.12). */
export function AppealSection() {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const state = useQuery({ queryKey: ["appeal"], queryFn: () => apiFetch<AppealState>("/me/appeal") });
  const send = useMutation({
    mutationFn: () =>
      apiFetch<AppealState>("/me/appeal", { method: "POST", body: JSON.stringify({ body: body.trim() }) }),
    onSuccess: (updated) => queryClient.setQueryData(["appeal"], updated),
    onError: (failed) => setError(errorText(failed)),
  });
  if (!state.isSuccess || !state.data.decision) return null;
  const { decision, appeal } = state.data;

  return (
    <div className="mt-6 flex flex-col gap-4 text-left">
      <Card padding="roomy" className="flex flex-col gap-2">
        <p className="text-small text-muted">
          {decision.action === "removed" ? "Closed" : "Paused"} on {when(decision.at)}
        </p>
        <p className="whitespace-pre-line text-ink">{decision.reason}</p>
      </Card>
      {appeal ? (
        <Card padding="roomy" className="flex flex-col gap-4">
          <p className="text-small text-muted">Your appeal · {when(appeal.created_at)}</p>
          <p className="whitespace-pre-line text-ink">{appeal.description}</p>
          {appeal.status === "open" || appeal.status === "replied" ? (
            <p className="text-muted">
              An admin who wasn't part of the decision will look at it and decide by {when(appeal.resolve_by)}.
            </p>
          ) : (
            <ComplaintState complaint={appeal} />
          )}
          <ComplaintThread complaint={appeal} refreshKey={["appeal"]} />
        </Card>
      ) : state.data.can_appeal && state.data.appeal_by ? (
        <Card padding="roomy">
          <form
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              if (!body.trim()) return setError("Please tell us why we should look at it again.");
              send.mutate();
            }}
            className="flex flex-col gap-3"
          >
            <Textarea
              label="Appeal this decision"
              hint={
                `Tell us why we should look at it again. You can appeal until ${when(state.data.appeal_by)}. ` +
                "An admin who wasn't part of the decision will review it within 7 working days."
              }
              maxLength={2000}
              value={body}
              onChange={(event) => setBody(event.target.value)}
            />
            {error && (
              <p role="alert" className="text-small text-danger">
                {error}
              </p>
            )}
            <div>
              <Button type="submit" loading={send.isPending} fullWidthOnPhone={false}>
                Send my appeal
              </Button>
            </div>
          </form>
        </Card>
      ) : (
        <p className="text-muted">The 15 days to appeal this decision have passed.</p>
      )}
    </div>
  );
}
