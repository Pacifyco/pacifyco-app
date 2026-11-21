import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { BackLink, Button, Card, Checkbox, EmptyState, Textarea, showToast } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDay, formatMobile, formatTime } from "../../lib/format";
import { errorMessage } from "./shared";

// Emergencies (CLAUDE.md 6.9): call both people, acknowledge (the alert across the admin panel goes), then
// resolve with what happened. A parent's theft or abuse report suspended the sitter: resolving decides
// whether she comes back. An open incident holds her payout for the booking.

export type AdminIncident = {
  id: string;
  kind: "emergency" | "theft" | "abuse" | "sitter_unsafe";
  status: "open" | "acknowledged";
  note: string | null;
  raised_by: "parent" | "sitter";
  created_at: string;
  suspended_sitter: boolean;
  sitter_status: string;
  booking_id: string;
  starts_at: string;
  ends_at: string;
  parent_name: string | null;
  parent_phone: string | null;
  sitter_name: string | null;
  sitter_phone: string | null;
};

export const INCIDENTS_KEY = ["admin", "incidents"];

export const KIND_WORDS: Record<AdminIncident["kind"], string> = {
  emergency: "Emergency",
  theft: "Theft",
  abuse: "Abuse",
  sitter_unsafe: "Sitter abused or unsafe",
};

function when(iso: string): string {
  const moment = new Date(iso);
  return `${formatDay(moment)}, ${formatTime(moment)}`;
}

function Person({ label, name, phone }: { label: string; name: string | null; phone: string | null }) {
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

type AdminMessage = { sender: "parent" | "sitter"; body: string; created_at: string };

/** Their chat, read only when handling the incident (6.11); every read is logged. */
function TheirChat({ incidentId }: { incidentId: string }) {
  const [open, setOpen] = useState(false);
  const chat = useQuery({
    queryKey: ["admin", "incident-chat", incidentId],
    queryFn: () => apiFetch<AdminMessage[]>(`/admin/incidents/${incidentId}/chat`),
    enabled: open,
  });
  if (!open) {
    return (
      <div>
        <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setOpen(true)}>
          Read their chat
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2 rounded-md bg-surface-sunken p-3">
      <p className="text-small text-muted">Reading this is logged.</p>
      {chat.isPending && <p className="text-muted">Loading…</p>}
      {chat.isSuccess && chat.data.length === 0 && <p className="text-ink">They haven't messaged each other.</p>}
      {chat.isSuccess && (
        <ul className="flex flex-col gap-2">
          {chat.data.map((message, index) => (
            <li key={index} className="text-small text-ink">
              <span className="font-semibold">{message.sender === "parent" ? "Parent" : "Sitter"}</span> ·{" "}
              {when(message.created_at)}: {message.body}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function IncidentItem({ incident }: { incident: AdminIncident }) {
  const queryClient = useQueryClient();
  const [resolving, setResolving] = useState(false);
  const [note, setNote] = useState("");
  const [reinstate, setReinstate] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const act = useMutation({
    mutationFn: (path: "acknowledge" | "resolve") =>
      apiFetch<AdminIncident>(`/admin/incidents/${incident.id}/${path}`, {
        method: "POST",
        ...(path === "resolve" ? { body: JSON.stringify({ note: note.trim(), reinstate_sitter: reinstate }) } : {}),
      }),
    onSuccess: async (_, path) => {
      showToast(path === "acknowledge" ? "Acknowledged" : "Resolved");
      await queryClient.invalidateQueries({ queryKey: INCIDENTS_KEY });
    },
    onError: (failed) => setError(errorMessage(failed)),
  });
  function resolve(event: FormEvent) {
    event.preventDefault();
    if (!note.trim()) return setError("Please say what happened.");
    setError(undefined);
    act.mutate("resolve");
  }
  return (
    <li className="flex flex-col gap-4 border-t border-line py-5 first:border-t-0">
      <div className="flex flex-col gap-1">
        <p className="text-eyebrow text-danger uppercase">
          {KIND_WORDS[incident.kind]} · from the {incident.raised_by} · {incident.status === "open" ? "not acknowledged" : "acknowledged"}
        </p>
        <p className="text-ui text-ink">
          Reported {when(incident.created_at)} · booking {when(incident.starts_at)} – {formatTime(new Date(incident.ends_at))}
        </p>
        {incident.note && <p className="text-ink">"{incident.note}"</p>}
        {incident.suspended_sitter && (
          <p className="text-small text-ink">
            The sitter's account was suspended by this report ({incident.sitter_status}).
          </p>
        )}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Person label="Parent" name={incident.parent_name} phone={incident.parent_phone} />
        <Person label="Sitter" name={incident.sitter_name} phone={incident.sitter_phone} />
      </div>
      <TheirChat incidentId={incident.id} />
      {resolving ? (
        <form noValidate onSubmit={resolve} className="flex flex-col gap-3">
          <Textarea
            label="What happened?"
            hint="Kept with the incident."
            rows={3}
            maxLength={1000}
            value={note}
            error={error}
            onChange={(event) => setNote(event.target.value)}
          />
          {incident.suspended_sitter && incident.sitter_status === "suspended" && (
            <Checkbox
              label="Make the sitter's account active again"
              checked={reinstate}
              onChange={(event) => setReinstate(event.target.checked)}
            />
          )}
          <div className="flex flex-wrap gap-3">
            <Button type="submit" variant="secondary" loading={act.isPending}>
              Resolve it
            </Button>
            <Button variant="tertiary" onClick={() => setResolving(false)}>
              Back
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-wrap gap-3">
          {incident.status === "open" && (
            <Button fullWidthOnPhone={false} loading={act.isPending} onClick={() => act.mutate("acknowledge")}>
              Acknowledge
            </Button>
          )}
          <Button variant="secondary" fullWidthOnPhone={false} onClick={() => setResolving(true)}>
            Resolve
          </Button>
        </div>
      )}
      {error && !resolving && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </li>
  );
}

export function IncidentsPage() {
  const incidents = useQuery({
    queryKey: INCIDENTS_KEY,
    queryFn: () => apiFetch<AdminIncident[]>("/admin/incidents"),
    refetchInterval: 30_000,
  });
  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-4">
      <BackLink to="/admin" label="Admin" />
      <h1>Emergencies</h1>
      {incidents.isPending && <p className="text-muted">Loading…</p>}
      {incidents.isError && (
        <p role="alert" className="text-danger">
          {errorMessage(incidents.error)}
        </p>
      )}
      {incidents.isSuccess &&
        (incidents.data.length === 0 ? (
          <EmptyState message="No emergencies open." />
        ) : (
          <Card as="section" padding="roomy" aria-label="Open emergencies">
            <ul>
              {incidents.data.map((incident) => (
                <IncidentItem key={incident.id} incident={incident} />
              ))}
            </ul>
          </Card>
        ))}
    </section>
  );
}
