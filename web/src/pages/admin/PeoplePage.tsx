import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { BackLink, Card, Select, TextInput } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDate } from "../../lib/format";
import { ACCOUNT_STATUS_WORDS, type AdminAccount } from "./AccountSection";
import { errorMessage } from "./shared";

// Find a parent or sitter by name, email or phone (phase 10 "User management"), to open their page and
// suspend, remove or reinstate them there.

export type PersonRow = {
  id: string;
  role: "parent" | "sitter";
  full_name: string | null;
  email: string;
  phone: string | null;
  status: AdminAccount["status"];
  created_at: string;
};

const ROLE_WORDS = { parent: "Parent", sitter: "Sitter" };

function useDebounced(value: string, delay = 300): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return settled;
}

export function PeoplePage() {
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get("q") ?? "");
  const role = params.get("role") ?? "";
  const status = params.get("status") ?? "";
  const q = useDebounced(text.trim());

  function setFilter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
  }

  const search = new URLSearchParams();
  if (q) search.set("q", q);
  if (role) search.set("role", role);
  if (status) search.set("status", status);
  const query = search.toString();
  const people = useQuery({
    queryKey: ["admin", "people", query],
    queryFn: () => apiFetch<PersonRow[]>(`/admin/people${query ? `?${query}` : ""}`),
    placeholderData: keepPreviousData,
  });

  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-6">
      <BackLink to="/admin" label="Admin" />
      <h1>People</h1>
      <Card padding="roomy" className="flex flex-col gap-4">
        <TextInput
          label="Name, email or phone"
          type="search"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setFilter("q", event.target.value.trim());
          }}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Select label="Role" value={role} onChange={(event) => setFilter("role", event.target.value)}>
            <option value="">Parents and sitters</option>
            <option value="parent">Parents</option>
            <option value="sitter">Sitters</option>
          </Select>
          <Select label="Account" value={status} onChange={(event) => setFilter("status", event.target.value)}>
            <option value="">Any</option>
            {(Object.keys(ACCOUNT_STATUS_WORDS) as AdminAccount["status"][]).map((item) => (
              <option key={item} value={item}>
                {ACCOUNT_STATUS_WORDS[item]}
              </option>
            ))}
          </Select>
        </div>
      </Card>
      {people.isPending && <p className="text-center text-muted">Loading…</p>}
      {people.isError && (
        <p role="alert" className="text-center text-danger">
          {errorMessage(people.error)}
        </p>
      )}
      {people.isSuccess &&
        (people.data.length === 0 ? (
          <p className="text-center text-muted">No one matches.</p>
        ) : (
          <Card padding="roomy">
            <ul aria-label="People">
              {people.data.map((person) => (
                <li key={person.id} className="border-t border-line first:border-t-0">
                  <Link
                    to={person.role === "sitter" ? `/admin/sitters/${person.id}` : `/admin/parents/${person.id}`}
                    className="flex items-center gap-4 py-4 text-ink no-underline"
                  >
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="text-ui">{person.full_name ?? person.email}</span>
                      <span className="truncate text-small text-muted">
                        {ROLE_WORDS[person.role]} · {[person.email, person.phone].filter(Boolean).join(" · ")} ·
                        joined{" "}
                        {formatDate(new Date(person.created_at))}
                      </span>
                    </span>
                    <span
                      className={
                        person.status === "suspended" || person.status === "removed"
                          ? "text-small text-danger"
                          : "text-small text-muted"
                      }
                    >
                      {ACCOUNT_STATUS_WORDS[person.status]}
                    </span>
                    <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-muted" />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        ))}
    </section>
  );
}
