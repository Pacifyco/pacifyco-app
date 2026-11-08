import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router";
import { Card } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDate, plural } from "../../lib/format";
import { errorMessage } from "./shared";

// The admin verification queue (CLAUDE.md 7): sitters still in onboarding, and families with a child
// whose birth certificate is waiting to be checked.

type SitterItem = {
  id: string;
  full_name: string | null; // filled in after sign-up (CLAUDE.md 6.13)
  email: string;
  signed_up_at: string;
  steps_approved: number;
  steps_total: number;
  level: string | null;
};

type FamilyItem = { id: string; full_name: string | null; email: string; signed_up_at: string; children_to_review: number };

export type VerificationQueue = { sitters: SitterItem[]; families: FamilyItem[] };

export const QUEUE_KEY = ["admin", "verifications"];

function QueueRow({ to, name, caption, status }: { to: string; name: string; caption: string; status: string }) {
  return (
    <li className="border-t border-line first:border-t-0">
      <Link to={to} className="flex items-center gap-4 py-4 text-ink no-underline">
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-ui">{name}</span>
          <span className="truncate text-small text-muted">{caption}</span>
        </span>
        <span className="text-small text-muted">{status}</span>
        <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-muted" />
      </Link>
    </li>
  );
}

export function VerificationQueuePage() {
  const queue = useQuery({ queryKey: QUEUE_KEY, queryFn: () => apiFetch<VerificationQueue>("/admin/verifications") });

  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-6">
      <div className="text-center">
        <h1>Verification queue</h1>
        <p className="mt-4 text-muted">Check each sitter's application and each child's birth certificate.</p>
      </div>
      {queue.isPending && <p className="text-center text-muted">Loading…</p>}
      {queue.isError && (
        <p role="alert" className="text-center text-danger">
          {errorMessage(queue.error)}
        </p>
      )}
      {queue.isSuccess && (
        <>
          <Card as="section" padding="roomy" aria-labelledby="sitters-heading">
            <h2 id="sitters-heading" className="text-h3">
              Sitters
            </h2>
            {queue.data.sitters.length === 0 ? (
              <p className="mt-3 text-muted">No sitters are waiting. Nice work.</p>
            ) : (
              <ul className="mt-3">
                {queue.data.sitters.map((sitter) => (
                  <QueueRow
                    key={sitter.id}
                    to={`/admin/sitters/${sitter.id}`}
                    name={sitter.full_name ?? sitter.email}
                    caption={`${sitter.email} · joined ${formatDate(new Date(sitter.signed_up_at))}`}
                    status={`${sitter.steps_approved} of ${sitter.steps_total} steps`}
                  />
                ))}
              </ul>
            )}
          </Card>
          <Card as="section" padding="roomy" aria-labelledby="families-heading">
            <h2 id="families-heading" className="text-h3">
              Families
            </h2>
            {queue.data.families.length === 0 ? (
              <p className="mt-3 text-muted">No birth certificates are waiting.</p>
            ) : (
              <ul className="mt-3">
                {queue.data.families.map((family) => (
                  <QueueRow
                    key={family.id}
                    to={`/admin/parents/${family.id}`}
                    name={family.full_name ?? family.email}
                    caption={`${family.email} · joined ${formatDate(new Date(family.signed_up_at))}`}
                    status={plural(family.children_to_review, "child to check", "children to check")}
                  />
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </section>
  );
}
