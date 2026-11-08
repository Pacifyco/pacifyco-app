import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { Button, Card, Select } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDate } from "../../lib/format";
import {
  BackToQueue,
  DecisionForm,
  type DocumentSummary,
  errorMessage,
  Field,
  type ReviewStatus,
  StatusPill,
  ViewDocumentButton,
} from "./shared";
import { QUEUE_KEY } from "./VerificationQueuePage";

// Reviewing one sitter (CLAUDE.md 7): each onboarding step, her references and psychology test, her
// level (6.2), then approval. She's live only once every step is approved and a level is set.

type StepName = "profile" | "identity_documents" | "police_certificate" | "references" | "psych_test";
type Level = "pause" | "unwind" | "recharge";

type Reference = {
  id: string;
  name: string;
  phone: string;
  relationship: string;
  outcome: ReviewStatus;
  notes: string | null;
};

type SitterReview = {
  id: string;
  full_name: string | null; // filled in after sign-up (CLAUDE.md 6.13)
  email: string;
  phone: string | null;
  pin_code: string | null;
  profile_status: string;
  signed_up_at: string;
  date_of_birth: string | null;
  bio: string | null;
  years_experience: number | null;
  age_groups: string[];
  languages: string[];
  first_aid: boolean;
  reference_shared_consent: boolean;
  has_health_disclosure: boolean;
  payout_method: "bank" | "upi" | null;
  onboarding_status: "in_progress" | "approved" | "rejected";
  level: Level | null;
  steps: Record<StepName, ReviewStatus>;
  documents: DocumentSummary[];
  references: Reference[];
  psych_attempt: { id: string; status: string; submitted_at: string | null } | null;
};

type PsychAnswer = { question_id: string; kind: string; prompt: string; options: string[] | null; answer_text: string | null };
type PsychAttemptDetail = { status: string; notes: string | null; retake_allowed: boolean; answers: PsychAnswer[] };

const STEP_LABELS: Record<StepName, string> = {
  profile: "Application and profile",
  identity_documents: "Government ID and college or work ID",
  police_certificate: "Police clearance certificate",
  references: "Two references",
  psych_test: "Psychology test",
};

// CLAUDE.md 6.2. Admins see the plan names; sitters never do.
const LEVELS: { value: Level; label: string }[] = [
  { value: "pause", label: "Pause (Level 1) · ₹200 an hour" },
  { value: "unwind", label: "Unwind (Level 2) · ₹300 an hour" },
  { value: "recharge", label: "Recharge (Level 3) · ₹400 an hour" },
];

const ONBOARDING_WORDS = { in_progress: "In onboarding", approved: "Approved and live", rejected: "Rejected" };

function sitterKey(id: string) {
  return ["admin", "sitter", id];
}

function Section({ title, status, children }: { title: string; status?: ReviewStatus; children: React.ReactNode }) {
  return (
    <Card as="section" padding="roomy">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-h3">{title}</h2>
        {status && <StatusPill status={status} />}
      </div>
      {children}
    </Card>
  );
}

function Checklist({ steps }: { steps: Record<StepName, ReviewStatus> }) {
  const names = Object.keys(STEP_LABELS) as StepName[];
  const done = names.filter((name) => steps[name] === "approved").length;
  return (
    <Section title="Onboarding steps">
      <p className="mt-2 text-small text-muted">
        {done} of {names.length} approved
      </p>
      <div
        className="mt-2 h-2 overflow-hidden rounded-pill bg-surface-sunken"
        role="progressbar"
        aria-label="Steps approved"
        aria-valuemin={0}
        aria-valuemax={names.length}
        aria-valuenow={done}
      >
        <div className="h-full bg-trust" style={{ width: `${(done / names.length) * 100}%` }} />
      </div>
      <ul className="mt-4">
        {names.map((name) => (
          <li key={name} className="flex items-center justify-between gap-3 border-t border-line py-3 first:border-t-0">
            <span className="text-body text-ink">{STEP_LABELS[name]}</span>
            <StatusPill status={steps[name]} />
          </li>
        ))}
      </ul>
    </Section>
  );
}

function HealthDisclosure({ sitterId, exists }: { sitterId: string; exists: boolean }) {
  const view = useMutation({
    mutationFn: () => apiFetch<{ disclosure: string | null }>(`/admin/sitters/${sitterId}/health-disclosure`),
  });
  if (!exists) return <>None given</>;
  if (view.isSuccess) return <span className="whitespace-pre-wrap">{view.data.disclosure ?? "None given"}</span>;
  return (
    <span className="flex flex-col items-start gap-2">
      <span className="text-small text-muted">Health data. Opening it is logged; never share it with parents.</span>
      <Button variant="secondary" fullWidthOnPhone={false} loading={view.isPending} onClick={() => view.mutate()}>
        Show health disclosure
      </Button>
      {view.isError && (
        <span role="alert" className="text-small text-danger">
          {errorMessage(view.error)}
        </span>
      )}
    </span>
  );
}

function PsychTest({ sitter, invalidate }: { sitter: SitterReview; invalidate: unknown[][] }) {
  const attempt = sitter.psych_attempt;
  const detail = useQuery({
    queryKey: ["admin", "psych-attempt", attempt?.id],
    queryFn: () => apiFetch<PsychAttemptDetail>(`/admin/psych-attempts/${attempt!.id}`),
    enabled: attempt !== null && attempt.status !== "in_progress",
  });

  return (
    <Section title={STEP_LABELS.psych_test} status={sitter.steps.psych_test}>
      {attempt === null && <p className="mt-3 text-muted">She hasn't started the test yet.</p>}
      {attempt?.status === "in_progress" && <p className="mt-3 text-muted">She's started but not submitted it yet.</p>}
      {detail.isSuccess && (
        <ol className="mt-4 flex flex-col gap-4">
          {detail.data.answers.map((answer) => (
            <li key={answer.question_id}>
              <p className="text-ui text-ink">{answer.prompt}</p>
              <p className="mt-1 whitespace-pre-wrap text-body text-ink">{answer.answer_text ?? "No answer"}</p>
            </li>
          ))}
        </ol>
      )}
      {attempt?.status === "submitted" && (
        <DecisionForm
          path={`/admin/psych-attempts/${attempt.id}/decision`}
          invalidate={invalidate}
          subject="the psychology test"
          approveLabel="Pass"
          rejectLabel="Fail"
          body={(approved, notes, rejectionReason) => ({ passed: approved, notes, rejection_reason: rejectionReason })}
        />
      )}
      {attempt?.status === "failed" && detail.isSuccess && (
        <AllowRetake attemptId={attempt.id} allowed={detail.data.retake_allowed} invalidate={invalidate} />
      )}
    </Section>
  );
}

// After a fail she can only try again once an admin allows it (decided 2026-11-08). Audit logged.
function AllowRetake({ attemptId, allowed, invalidate }: { attemptId: string; allowed: boolean; invalidate: unknown[][] }) {
  const queryClient = useQueryClient();
  const allow = useMutation({
    mutationFn: () => apiFetch<unknown>(`/admin/psych-attempts/${attemptId}/allow-retake`, { method: "POST" }),
    onSuccess: () => Promise.all(invalidate.map((queryKey) => queryClient.invalidateQueries({ queryKey }))),
  });
  if (allowed) return <p className="mt-4 text-small text-muted">You've allowed her to take it again.</p>;
  return (
    <div className="mt-4 flex flex-col items-start gap-2">
      <p className="text-small text-muted">She failed. She can only take it again if you allow it.</p>
      <Button variant="secondary" fullWidthOnPhone={false} loading={allow.isPending} onClick={() => allow.mutate()}>
        Allow a retake
      </Button>
      {allow.isError && (
        <p role="alert" className="text-small text-danger">
          {errorMessage(allow.error)}
        </p>
      )}
    </div>
  );
}

function LevelPicker({ sitter, invalidate }: { sitter: SitterReview; invalidate: unknown[][] }) {
  const queryClient = useQueryClient();
  const [level, setLevel] = useState<Level | "">(sitter.level ?? "");
  const save = useMutation({
    mutationFn: (value: Level) =>
      apiFetch<unknown>(`/admin/sitters/${sitter.id}/level`, { method: "PUT", body: JSON.stringify({ level: value }) }),
    onSuccess: () => Promise.all(invalidate.map((queryKey) => queryClient.invalidateQueries({ queryKey }))),
  });

  return (
    <form
      className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end"
      onSubmit={(event) => {
        event.preventDefault();
        if (level) save.mutate(level);
      }}
    >
      <div className="flex-1">
        <Select label="Level" value={level} onChange={(event) => setLevel(event.target.value as Level | "")}>
          <option value="">Choose a level</option>
          {LEVELS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </div>
      <Button type="submit" variant="secondary" fullWidthOnPhone={false} loading={save.isPending} disabled={!level}>
        Save level
      </Button>
      {save.isError && (
        <p role="alert" className="text-small text-danger">
          {errorMessage(save.error)}
        </p>
      )}
    </form>
  );
}

function documentsOf(sitter: SitterReview, ...types: string[]) {
  return sitter.documents.filter((doc) => types.includes(doc.type));
}

function DocumentList({ documents }: { documents: DocumentSummary[] }) {
  if (documents.length === 0) return <p className="mt-3 text-muted">Nothing uploaded yet.</p>;
  return (
    <ul className="mt-3 flex flex-wrap gap-3">
      {documents.map((doc) => (
        <li key={doc.id}>
          <ViewDocumentButton document={doc} />
        </li>
      ))}
    </ul>
  );
}

export function SitterReviewPage() {
  const { sitterId = "" } = useParams();
  const key = sitterKey(sitterId);
  const invalidate = [key, QUEUE_KEY];
  const review = useQuery({ queryKey: key, queryFn: () => apiFetch<SitterReview>(`/admin/sitters/${sitterId}`) });

  if (review.isPending) return <p className="text-center text-muted">Loading…</p>;
  if (review.isError)
    return (
      <p role="alert" className="text-center text-danger">
        {errorMessage(review.error)}
      </p>
    );

  const sitter = review.data;
  const stepPath = (step: StepName) => `/admin/sitters/${sitter.id}/steps/${step}`;

  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-6">
      <BackToQueue />
      <div>
        <h1>{sitter.full_name ?? sitter.email}</h1>
        <p className="mt-2 text-muted">
          {[sitter.email, sitter.phone, sitter.pin_code].filter(Boolean).join(" · ")} · joined{" "}
          {formatDate(new Date(sitter.signed_up_at))} · {ONBOARDING_WORDS[sitter.onboarding_status]}
        </p>
      </div>

      <Checklist steps={sitter.steps} />

      <Section title={STEP_LABELS.profile} status={sitter.steps.profile}>
        <dl className="mt-4 flex flex-col gap-3">
          <Field label="Date of birth">
            {sitter.date_of_birth ? formatDate(new Date(sitter.date_of_birth)) : "Not given"}
          </Field>
          <Field label="Experience">
            {sitter.years_experience === null ? "Not given" : `${sitter.years_experience} years`}
          </Field>
          <Field label="Age groups">{sitter.age_groups.join(", ") || "Not given"}</Field>
          <Field label="Languages">{sitter.languages.join(", ") || "Not given"}</Field>
          <Field label="First aid">{sitter.first_aid ? "Certified" : "No"}</Field>
          <Field label="Reference shared at Recharge">{sitter.reference_shared_consent ? "Yes, she agreed" : "No"}</Field>
          <Field label="About her">
            <span className="whitespace-pre-wrap">{sitter.bio ?? "Not given"}</span>
          </Field>
          <Field label="Payout">
            {sitter.payout_method === "bank" ? "Bank account" : sitter.payout_method === "upi" ? "UPI" : "Not given"}
          </Field>
          <Field label="Health">
            <HealthDisclosure sitterId={sitter.id} exists={sitter.has_health_disclosure} />
          </Field>
        </dl>
        <DocumentList documents={documentsOf(sitter, "first_aid_certificate", "photo")} />
        <DecisionForm path={stepPath("profile")} invalidate={invalidate} subject="the profile" />
      </Section>

      <Section title={STEP_LABELS.identity_documents} status={sitter.steps.identity_documents}>
        <DocumentList documents={documentsOf(sitter, "government_id", "college_or_work_id")} />
        <DecisionForm path={stepPath("identity_documents")} invalidate={invalidate} subject="the ID documents" />
      </Section>

      <Section title={STEP_LABELS.police_certificate} status={sitter.steps.police_certificate}>
        <DocumentList documents={documentsOf(sitter, "police_certificate")} />
        <DecisionForm path={stepPath("police_certificate")} invalidate={invalidate} subject="the police certificate" />
      </Section>

      <Section title={STEP_LABELS.references} status={sitter.steps.references}>
        {sitter.references.length === 0 && <p className="mt-3 text-muted">No references added yet.</p>}
        <ul className="mt-2">
          {sitter.references.map((reference) => (
            <li key={reference.id} className="border-t border-line py-4 first:border-t-0">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span>
                  <span className="text-ui text-ink">{reference.name}</span>
                  <span className="block text-small text-muted">
                    {reference.relationship} · <a href={`tel:${reference.phone}`}>{reference.phone}</a>
                  </span>
                </span>
                <StatusPill status={reference.outcome} />
              </div>
              {reference.notes && <p className="mt-2 text-small text-muted">Notes: {reference.notes}</p>}
              <DecisionForm
                path={`/admin/references/${reference.id}/decision`}
                invalidate={invalidate}
                subject={`${reference.name}'s reference`}
              />
            </li>
          ))}
        </ul>
      </Section>

      <PsychTest sitter={sitter} invalidate={[...invalidate, ["admin", "psych-attempt", sitter.psych_attempt?.id]]} />

      <Section title="Level and approval">
        <p className="mt-2 text-small text-muted">
          She works only her own level's plan. She goes live once every step is approved and her level is set.
        </p>
        <LevelPicker key={sitter.level ?? "none"} sitter={sitter} invalidate={invalidate} />
        <DecisionForm
          path={`/admin/sitters/${sitter.id}/decision`}
          invalidate={invalidate}
          subject="this sitter"
          approveLabel="Approve and go live"
          rejectLabel="Reject application"
        />
      </Section>
    </section>
  );
}
