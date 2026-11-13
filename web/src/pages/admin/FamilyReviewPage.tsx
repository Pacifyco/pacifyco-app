import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { Card } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDate } from "../../lib/format";
import {
  BackToQueue,
  DecisionForm,
  type DocumentSummary,
  errorMessage,
  type ReviewStatus,
  StatusPill,
  ViewDocumentButton,
} from "./shared";
import { QUEUE_KEY } from "./VerificationQueuePage";

// Checking a family's birth certificates (CLAUDE.md 7). Approving a child deletes the certificate at
// once, keeping only the status, who verified it and when.

type ChildReview = {
  id: string;
  name: string;
  date_of_birth: string;
  verification_status: ReviewStatus;
  verified_at: string | null;
  verification_notes: string | null;
  rejection_reason: string | null;
  birth_certificates: DocumentSummary[];
};

type FamilyReview = {
  id: string;
  full_name: string | null; // filled in after sign-up (CLAUDE.md 6.13)
  email: string;
  phone: string | null;
  pin_code: string | null;
  verification_status: ReviewStatus;
  signed_up_at: string;
  children: ChildReview[];
};

function ChildCard({ child, invalidate }: { child: ChildReview; invalidate: unknown[][] }) {
  const [latest] = child.birth_certificates;
  return (
    <Card as="li" padding="roomy">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>
          <h2 className="text-h3">{child.name}</h2>
          <span className="text-small text-muted">Born {formatDate(new Date(child.date_of_birth))}</span>
        </span>
        <StatusPill status={child.verification_status} />
      </div>
      {child.verification_notes && <p className="mt-3 text-small text-muted">Notes: {child.verification_notes}</p>}
      {child.verification_status === "rejected" && child.rejection_reason && (
        <p className="mt-1 text-small text-muted">Reason given to the parent: {child.rejection_reason}</p>
      )}

      {child.verification_status === "approved" ? (
        <p className="mt-3 text-small text-muted">
          Verified{child.verified_at ? ` on ${formatDate(new Date(child.verified_at))}` : ""}. The birth certificate
          has been deleted.
        </p>
      ) : latest ? (
        <>
          <p className="mt-3 text-small text-muted">
            Check the name and date of birth match the certificate. Approving deletes the certificate.
          </p>
          <div className="mt-3">
            <ViewDocumentButton document={latest} />
          </div>
          <DecisionForm
            path={`/admin/children/${child.id}/decision`}
            invalidate={invalidate}
            subject={`${child.name}'s birth certificate`}
          />
        </>
      ) : (
        <p className="mt-3 text-muted">No birth certificate uploaded yet.</p>
      )}
    </Card>
  );
}

export function FamilyReviewPage() {
  const { parentId = "" } = useParams();
  const key = ["admin", "family", parentId];
  const review = useQuery({ queryKey: key, queryFn: () => apiFetch<FamilyReview>(`/admin/parents/${parentId}`) });

  if (review.isPending) return <p className="text-center text-muted">Loading…</p>;
  if (review.isError)
    return (
      <p role="alert" className="text-center text-danger">
        {errorMessage(review.error)}
      </p>
    );

  const family = review.data;
  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-6">
      <BackToQueue />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1>{family.full_name ?? family.email}</h1>
          <p className="mt-2 text-muted">
            {[family.email, family.phone, family.pin_code].filter(Boolean).join(" · ")} · joined{" "}
            {formatDate(new Date(family.signed_up_at))}
          </p>
        </div>
        <StatusPill status={family.verification_status} />
      </div>
      {family.children.length === 0 ? (
        <p className="text-muted">No children added yet.</p>
      ) : (
        <ul className="flex flex-col gap-6">
          {family.children.map((child) => (
            <ChildCard key={child.id} child={child} invalidate={[key, QUEUE_KEY]} />
          ))}
        </ul>
      )}
    </section>
  );
}
