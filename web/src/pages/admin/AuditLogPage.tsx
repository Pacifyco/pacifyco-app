import { useState } from "react";
import { Link } from "react-router";
import { BackLink, Card, Select, TextInput } from "../../components/ui";
import { rupees } from "../../lib/prices";
import { adminStatusText } from "./BookingsPage";
import { AdminSelect, DateFilters, ShowMore, personPath, useDebounced, useFilters, usePagedLog, when } from "./logs";
import type { LogPerson } from "./logs";
import { errorMessage } from "./shared";

// The audit log, for admins (phase 10; CLAUDE.md 5): every state change, newest first, 50 at a time. Read
// only: the log can only be added to. Filter by who did it, the kind of record, one record, words in the
// action and dates.

export type AuditEntry = {
  id: number;
  at: string;
  by: string | null; // null: the rules did it (a scheduled job or an automatic step)
  by_id: string | null;
  action: string;
  entity: string;
  entity_id: string;
  person: LogPerson | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
};

type AuditLogPage = { entries: AuditEntry[]; more: boolean };

export const RECORD_WORDS: Record<string, string> = {
  booking: "Booking",
  payment: "Payment",
  sitter_earning: "Sitter earning",
  payout: "Payout",
  strike: "Strike",
  profiles: "Account",
  sitters: "Sitter",
  parents: "Family",
  children: "Child",
  onboarding_steps: "Onboarding step",
  references: "Reference",
  psych_attempts: "Psychology screening",
  incident: "Emergency",
  complaint: "Issue",
  booking_report: "Report",
  overtime_request: "Overtime request",
  rating_flag: "Low-rating flag",
  review: "Review",
};

/** A value from before or after, in plain words. */
export function valueText(key: string, value: unknown): string {
  if (value === null || value === undefined) return "none";
  if (key.endsWith("_paise") && typeof value === "number") return rupees(value);
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function Changes({ before, after }: { before: AuditEntry["before"]; after: AuditEntry["after"] }) {
  const keys = [...new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])];
  if (keys.length === 0) return null;
  return (
    <ul className="text-small text-muted">
      {keys.map((key) => {
        const was = before && key in before ? `${valueText(key, before[key])} → ` : "";
        const now = after && key in after ? valueText(key, after[key]) : "removed";
        return (
          <li key={key} className="break-words">
            {adminStatusText(key)}: {was}
            {now}
          </li>
        );
      })}
    </ul>
  );
}

function Subject({ entry }: { entry: AuditEntry }) {
  const record = RECORD_WORDS[entry.entity] ?? adminStatusText(entry.entity);
  if (entry.person) {
    const path = personPath(entry.person);
    const name = entry.person.full_name || "No name yet";
    return (
      <>
        {record}: {path ? <Link to={path}>{name}</Link> : name}
      </>
    );
  }
  if (entry.entity === "booking") return <Link to={`/admin/bookings/${entry.entity_id}`}>Booking</Link>;
  return (
    <>
      {record} <span className="break-all">{entry.entity_id}</span>
    </>
  );
}

export function AuditLogPage() {
  const { get, setFilter, pages, showMore } = useFilters();
  const [words, setWords] = useState(get("action"));
  const [record, setRecord] = useState(get("record"));
  const action = useDebounced(words.trim());
  const entityId = useDebounced(record.trim());

  const search = new URLSearchParams();
  if (get("by")) search.set("by", get("by"));
  if (get("entity")) search.set("entity", get("entity"));
  if (entityId) search.set("entity_id", entityId);
  if (action) search.set("action", action);
  if (get("from")) search.set("on_from", get("from"));
  if (get("to")) search.set("on_to", get("to"));
  const log = usePagedLog("/admin/audit-log", search.toString(), pages, (page: AuditLogPage) => page.entries);

  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-6">
      <BackLink to="/admin" label="Admin" />
      <h1>Audit log</h1>
      <Card padding="roomy" className="flex flex-col gap-4">
        <AdminSelect label="Done by" value={get("by")} withRules onChange={(value) => setFilter("by", value)} />
        <Select
          label="Kind of record"
          value={get("entity")}
          onChange={(event) => setFilter("entity", event.target.value)}
        >
          <option value="">Every kind</option>
          {Object.entries(RECORD_WORDS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <TextInput
          label="Record id"
          hint="The id from its page's address, for everything that happened to one record."
          value={record}
          onChange={(event) => {
            setRecord(event.target.value);
            setFilter("record", event.target.value.trim());
          }}
        />
        <TextInput
          label="What happened"
          hint="Words in the action, like “refund” or “strike”."
          type="search"
          value={words}
          onChange={(event) => {
            setWords(event.target.value);
            setFilter("action", event.target.value.trim());
          }}
        />
        <DateFilters from={get("from")} to={get("to")} setFilter={setFilter} />
      </Card>
      {log.isPending && <p className="text-center text-muted">Loading…</p>}
      {log.isError && (
        <p role="alert" className="text-center text-danger">
          {errorMessage(log.error)}
        </p>
      )}
      {log.isSuccess &&
        (log.data.items.length === 0 ? (
          <p className="text-center text-muted">Nothing matches.</p>
        ) : (
          <Card padding="roomy" className="flex flex-col gap-3">
            <ul aria-label="Audit log">
              {log.data.items.map((entry) => (
                <li key={entry.id} className="flex flex-col gap-1 border-t border-line py-3 first:border-t-0">
                  <p className="text-ui text-ink">{adminStatusText(entry.action)}</p>
                  <p className="text-small">
                    <Subject entry={entry} />
                  </p>
                  <p className="text-small text-muted">
                    {entry.by ?? "The rules"} · {when(entry.at)}
                  </p>
                  <Changes before={entry.before} after={entry.after} />
                </li>
              ))}
            </ul>
            {log.data.more && <ShowMore loading={log.isFetching} onClick={showMore} />}
          </Card>
        ))}
    </section>
  );
}
