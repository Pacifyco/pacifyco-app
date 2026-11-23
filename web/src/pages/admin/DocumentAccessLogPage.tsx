import { useState } from "react";
import { Link } from "react-router";
import { BackLink, Card, Select, TextInput } from "../../components/ui";
import { AdminSelect, DateFilters, ShowMore, personPath, useDebounced, useFilters, usePagedLog, when } from "./logs";
import type { LogPerson } from "./logs";
import { DOCUMENT_LABELS, errorMessage } from "./shared";

// The document access log, for admins (phase 10; CLAUDE.md 5 and 7): every time an admin opened a
// document, newest first, 50 at a time. Read only. Filter by the admin, the type, the owner and dates.

export type DocumentView = {
  id: number;
  at: string;
  admin_name: string | null;
  admin_id: string;
  document_id: string;
  document_type: string;
  deleted: boolean; // the file has since been deleted (birth certificates, once the child is verified)
  owner: LogPerson;
  child_name: string | null;
};

type DocumentViewsPage = { views: DocumentView[]; more: boolean };

export function DocumentAccessLogPage() {
  const { get, setFilter, pages, showMore } = useFilters();
  const [text, setText] = useState(get("owner"));
  const owner = useDebounced(text.trim());

  const search = new URLSearchParams();
  if (get("admin")) search.set("admin_id", get("admin"));
  if (get("type")) search.set("document_type", get("type"));
  if (owner) search.set("owner", owner);
  if (get("from")) search.set("on_from", get("from"));
  if (get("to")) search.set("on_to", get("to"));
  const log = usePagedLog(
    "/admin/document-access-log",
    search.toString(),
    pages,
    (page: DocumentViewsPage) => page.views,
  );

  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-6">
      <BackLink to="/admin" label="Admin" />
      <h1>Document access log</h1>
      <Card padding="roomy" className="flex flex-col gap-4">
        <TextInput
          label="Whose document (their name)"
          type="search"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setFilter("owner", event.target.value.trim());
          }}
        />
        <AdminSelect label="Opened by" value={get("admin")} onChange={(value) => setFilter("admin", value)} />
        <Select label="Document" value={get("type")} onChange={(event) => setFilter("type", event.target.value)}>
          <option value="">Every document</option>
          {Object.entries(DOCUMENT_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
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
            <ul aria-label="Document access log">
              {log.data.items.map((view) => {
                const path = personPath(view.owner);
                const name = view.owner.full_name || "No name yet";
                return (
                  <li key={view.id} className="flex flex-col gap-1 border-t border-line py-3 first:border-t-0">
                    <p className="text-ui text-ink">
                      {DOCUMENT_LABELS[view.document_type] ?? view.document_type}
                      {view.child_name ? ` for ${view.child_name}` : ""} ·{" "}
                      {path ? <Link to={path}>{name}</Link> : name}
                    </p>
                    <p className="text-small text-muted">
                      Opened by {view.admin_name || "an admin"} · {when(view.at)}
                      {view.deleted ? " · File since deleted" : ""}
                    </p>
                  </li>
                );
              })}
            </ul>
            {log.data.more && <ShowMore loading={log.isFetching} onClick={showMore} />}
          </Card>
        ))}
    </section>
  );
}
