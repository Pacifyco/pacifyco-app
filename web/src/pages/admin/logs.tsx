import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { Button, Select, TextInput } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDay, formatTime } from "../../lib/format";

// Pieces shared by the audit log and document access log pages (phase 10): filters kept in the address,
// 50 entries a page with "Show more".

export type AdminOption = { id: string; full_name: string | null };

export type LogPerson = { id: string; full_name: string | null; role: "parent" | "sitter" | "admin" };

export function when(iso: string): string {
  const moment = new Date(iso);
  return `${formatDay(moment)}, ${formatTime(moment)}`;
}

/** Their admin page, for a parent or sitter. */
export function personPath(person: LogPerson): string | null {
  if (person.role === "sitter") return `/admin/sitters/${person.id}`;
  if (person.role === "parent") return `/admin/parents/${person.id}`;
  return null;
}

export function useDebounced(value: string, delay = 300): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return settled;
}

/** The filters, kept in the address so a filtered log can be shared or reloaded. */
export function useFilters() {
  const [params, setParams] = useSearchParams();
  const [pages, setPages] = useState(1);
  function setFilter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
    setPages(1);
  }
  return { get: (name: string) => params.get(name) ?? "", setFilter, pages, showMore: () => setPages((n) => n + 1) };
}

/** Every page loaded so far of a list, as one list. */
export function usePagedLog<Page extends { more: boolean }, Item>(
  path: string,
  query: string,
  pages: number,
  items: (page: Page) => Item[],
) {
  return useQuery({
    queryKey: ["admin", path, query, pages],
    queryFn: async () => {
      const found = await Promise.all(
        Array.from({ length: pages }, (_, page) =>
          apiFetch<Page>(`${path}?${[query, `page=${page}`].filter(Boolean).join("&")}`),
        ),
      );
      return { items: found.flatMap(items), more: found[found.length - 1].more };
    },
    placeholderData: keepPreviousData,
  });
}

export function useAdmins() {
  return useQuery({ queryKey: ["admin", "admins"], queryFn: () => apiFetch<AdminOption[]>("/admin/admins") });
}

export function DateFilters({
  from,
  to,
  setFilter,
}: {
  from: string;
  to: string;
  setFilter: (name: string, value: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <TextInput label="From" type="date" value={from} onChange={(event) => setFilter("from", event.target.value)} />
      <TextInput label="Until" type="date" value={to} onChange={(event) => setFilter("to", event.target.value)} />
    </div>
  );
}

export function AdminSelect({
  label,
  value,
  onChange,
  withRules = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  withRules?: boolean;
}) {
  const admins = useAdmins();
  return (
    <Select label={label} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">Anyone</option>
      {withRules && <option value="rules">The rules (automatic)</option>}
      {(admins.data ?? []).map((admin) => (
        <option key={admin.id} value={admin.id}>
          {admin.full_name || "An admin"}
        </option>
      ))}
    </Select>
  );
}

export function ShowMore({ loading, onClick }: { loading: boolean; onClick: () => void }) {
  return (
    <div>
      <Button variant="tertiary" fullWidthOnPhone={false} loading={loading} onClick={onClick}>
        Show more
      </Button>
    </div>
  );
}
