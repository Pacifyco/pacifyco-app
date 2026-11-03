import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { DocumentUpload } from "../components/documents/DocumentUpload";
import { Button, ButtonLink, Card, Checkbox, Select, TextInput, Textarea } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";

// ---------- shared bits ----------

function ErrorLine({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p role="alert" className="text-small text-danger">
      {message}
    </p>
  );
}

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

// ---------- profile (CLAUDE.md section 7 step 1) ----------

type OnboardingStatus = "in_progress" | "approved" | "rejected";

type SitterProfile = {
  date_of_birth: string | null;
  bio: string | null;
  years_experience: number | null;
  age_groups: string[];
  languages: string[];
  first_aid: boolean;
  onboarding_status: OnboardingStatus;
};

type ProfileInput = {
  date_of_birth: string;
  bio: string;
  years_experience: string;
  age_groups: string;
  languages: string;
  first_aid: boolean;
};

function profileInput(profile: SitterProfile): ProfileInput {
  return {
    date_of_birth: profile.date_of_birth ?? "",
    bio: profile.bio ?? "",
    years_experience: profile.years_experience !== null ? String(profile.years_experience) : "",
    age_groups: profile.age_groups.join(", "),
    languages: profile.languages.join(", "),
    first_aid: profile.first_aid,
  };
}

function toProfileBody(input: ProfileInput) {
  return {
    date_of_birth: input.date_of_birth,
    bio: input.bio.trim() || null,
    years_experience: Number(input.years_experience),
    age_groups: splitList(input.age_groups),
    languages: splitList(input.languages),
    first_aid: input.first_aid,
  };
}

const STATUS_LABEL: Record<OnboardingStatus, string> = {
  in_progress: "Application in progress",
  approved: "Approved",
  rejected: "Not approved",
};

function StatusPill({ status }: { status: OnboardingStatus }) {
  return <span className="inline-flex items-center rounded-pill bg-surface-sunken px-3 py-1 text-small text-ink">{STATUS_LABEL[status]}</span>;
}

function useSitterProfile() {
  return useQuery({ queryKey: ["sitter-profile"], queryFn: () => apiFetch<SitterProfile>("/sitter/profile") });
}

function ProfileForm({ initial, status }: { initial: ProfileInput; status: OnboardingStatus }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(initial);
  const [error, setError] = useState<string>();

  const save = useMutation({
    mutationFn: () =>
      apiFetch<SitterProfile>("/sitter/profile", { method: "PUT", body: JSON.stringify(toProfileBody(form)) }),
    onSuccess: () => {
      setError(undefined);
      queryClient.invalidateQueries({ queryKey: ["sitter-profile"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again."),
  });

  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-h3">Your profile</h2>
        <StatusPill status={status} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <TextInput
          label="Date of birth"
          type="date"
          value={form.date_of_birth}
          onChange={(event) => setForm({ ...form, date_of_birth: event.target.value })}
        />
        <TextInput
          label="Years of experience"
          type="number"
          min={0}
          max={80}
          value={form.years_experience}
          onChange={(event) => setForm({ ...form, years_experience: event.target.value })}
        />
      </div>
      <Textarea
        label="About you"
        optional
        hint="What parents will see on your profile."
        value={form.bio}
        onChange={(event) => setForm({ ...form, bio: event.target.value })}
      />
      <TextInput
        label="Age groups you care for"
        hint="Comma-separated, e.g. Infant, Toddler, Preschool."
        value={form.age_groups}
        onChange={(event) => setForm({ ...form, age_groups: event.target.value })}
      />
      <TextInput
        label="Languages you speak"
        hint="Comma-separated, e.g. English, Kannada, Hindi."
        value={form.languages}
        onChange={(event) => setForm({ ...form, languages: event.target.value })}
      />
      <Checkbox
        label="I'm first-aid certified"
        checked={form.first_aid}
        onChange={(event) => setForm({ ...form, first_aid: event.target.checked })}
      />
      <ErrorLine message={error} />
      <Button type="button" fullWidthOnPhone={false} loading={save.isPending} onClick={() => save.mutate()}>
        Save profile
      </Button>
    </>
  );
}

function ProfileSection() {
  const profile = useSitterProfile();
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-5">
      {profile.isPending && <p className="text-muted">Loading…</p>}
      {profile.data && <ProfileForm initial={profileInput(profile.data)} status={profile.data.onboarding_status} />}
    </Card>
  );
}

// ---------- health disclosure (CLAUDE.md section 7: encrypted, admin-only, never shown to parents) ----------

function useHealthDisclosure() {
  return useQuery({
    queryKey: ["health-disclosure"],
    queryFn: () => apiFetch<{ disclosure: string | null }>("/sitter/health-disclosure"),
  });
}

function HealthDisclosureForm({ initial }: { initial: string }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(initial);
  const [error, setError] = useState<string>();

  const save = useMutation({
    mutationFn: () =>
      apiFetch<{ disclosure: string | null }>("/sitter/health-disclosure", {
        method: "PUT",
        body: JSON.stringify({ disclosure: value.trim() || null }),
      }),
    onSuccess: () => {
      setError(undefined);
      queryClient.invalidateQueries({ queryKey: ["health-disclosure"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again."),
  });

  return (
    <>
      <Textarea
        label="Health disclosure"
        optional
        hint="Any serious or long-term condition or allergy that could affect safe care. Only Pacify admins can see this — never shown to parents, and used only to match you safely."
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      <ErrorLine message={error} />
      <Button type="button" fullWidthOnPhone={false} loading={save.isPending} onClick={() => save.mutate()}>
        Save
      </Button>
    </>
  );
}

function HealthDisclosureSection() {
  const disclosure = useHealthDisclosure();
  return (
    <Card as="section" className="flex flex-col gap-5">
      <h2 className="text-h3">Health disclosure</h2>
      {disclosure.isPending && <p className="text-small text-muted">Loading…</p>}
      {disclosure.data && <HealthDisclosureForm initial={disclosure.data.disclosure ?? ""} />}
    </Card>
  );
}

// ---------- payout details (CLAUDE.md sections 6.2 and 7: bank account or UPI) ----------

type PayoutMethod = "bank" | "upi";

type PayoutDetails = {
  method: PayoutMethod | null;
  account_holder_name: string | null;
  account_number: string | null;
  ifsc_code: string | null;
  upi_id: string | null;
};

type PayoutInput = {
  method: PayoutMethod;
  account_holder_name: string;
  account_number: string;
  ifsc_code: string;
  upi_id: string;
};

function payoutInput(details: PayoutDetails): PayoutInput {
  return {
    method: details.method ?? "upi",
    account_holder_name: details.account_holder_name ?? "",
    account_number: details.account_number ?? "",
    ifsc_code: details.ifsc_code ?? "",
    upi_id: details.upi_id ?? "",
  };
}

function usePayoutDetails() {
  return useQuery({
    queryKey: ["payout-details"],
    queryFn: () => apiFetch<PayoutDetails>("/sitter/payout-details"),
  });
}

function PayoutDetailsForm({ initial }: { initial: PayoutInput }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(initial);
  const [error, setError] = useState<string>();

  const save = useMutation({
    mutationFn: () => {
      const body =
        form.method === "bank"
          ? {
              method: "bank",
              account_holder_name: form.account_holder_name,
              account_number: form.account_number,
              ifsc_code: form.ifsc_code,
            }
          : { method: "upi", upi_id: form.upi_id };
      return apiFetch<PayoutDetails>("/sitter/payout-details", { method: "PUT", body: JSON.stringify(body) });
    },
    onSuccess: () => {
      setError(undefined);
      queryClient.invalidateQueries({ queryKey: ["payout-details"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again."),
  });

  return (
    <>
      <Select
        label="Payout method"
        value={form.method}
        onChange={(event) => setForm({ ...form, method: event.target.value as PayoutMethod })}
      >
        <option value="upi">UPI</option>
        <option value="bank">Bank account</option>
      </Select>
      {form.method === "bank" ? (
        <>
          <TextInput
            label="Account holder name"
            value={form.account_holder_name}
            onChange={(event) => setForm({ ...form, account_holder_name: event.target.value })}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextInput
              label="Account number"
              value={form.account_number}
              onChange={(event) => setForm({ ...form, account_number: event.target.value })}
            />
            <TextInput
              label="IFSC code"
              value={form.ifsc_code}
              onChange={(event) => setForm({ ...form, ifsc_code: event.target.value.toUpperCase() })}
            />
          </div>
        </>
      ) : (
        <TextInput
          label="UPI ID"
          value={form.upi_id}
          onChange={(event) => setForm({ ...form, upi_id: event.target.value })}
        />
      )}
      <ErrorLine message={error} />
      <Button type="button" fullWidthOnPhone={false} loading={save.isPending} onClick={() => save.mutate()}>
        Save payout details
      </Button>
    </>
  );
}

function PayoutDetailsSection() {
  const details = usePayoutDetails();
  return (
    <Card as="section" className="flex flex-col gap-5">
      <div>
        <h2 className="text-h3">Payout details</h2>
        <p className="mt-1 text-small text-muted">How Pacify pays you, within 12 hours of each booking.</p>
      </div>
      {details.isPending && <p className="text-small text-muted">Loading…</p>}
      {details.data && <PayoutDetailsForm initial={payoutInput(details.data)} />}
    </Card>
  );
}

// ---------- references (CLAUDE.md section 7 step 4) ----------

type ReferenceOutcome = "pending" | "approved" | "rejected";
type Reference = { id: string; name: string; relationship: string; phone: string; outcome: ReferenceOutcome };
type ReferenceInput = { name: string; relationship: string; phone: string };
const EMPTY_REFERENCE: ReferenceInput = { name: "", relationship: "", phone: "" };
const MAX_REFERENCES = 2;

function ReferencesSection() {
  const queryClient = useQueryClient();
  const references = useQuery({ queryKey: ["references"], queryFn: () => apiFetch<Reference[]>("/sitter/references") });
  const [form, setForm] = useState<ReferenceInput>(EMPTY_REFERENCE);
  const [error, setError] = useState<string>();

  const add = useMutation({
    mutationFn: (input: ReferenceInput) =>
      apiFetch<Reference>("/sitter/references", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["references"] });
      setForm(EMPTY_REFERENCE);
      setError(undefined);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again."),
  });

  const remove = useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/sitter/references/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["references"] }),
  });

  const count = references.data?.length ?? 0;

  return (
    <Card as="section" className="flex flex-col gap-5">
      <div>
        <h2 className="text-h3">References</h2>
        <p className="mt-1 text-small text-muted">Two people who can vouch for you. Pacify will contact them.</p>
      </div>
      {references.isSuccess && references.data.length > 0 && (
        <ul className="flex flex-col gap-2">
          {references.data.map((reference) => (
            <li key={reference.id} className="flex items-center gap-3 rounded-md bg-surface-sunken px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-ui text-ink">{reference.name}</p>
                <p className="text-small text-muted">
                  {reference.relationship} · {reference.phone}
                </p>
              </div>
              <button
                type="button"
                aria-label={`Remove ${reference.name}`}
                onClick={() => remove.mutate(reference.id)}
                className="inline-flex size-9 shrink-0 items-center justify-center rounded-pill text-muted hover:text-danger"
              >
                <Trash2 aria-hidden="true" size={18} strokeWidth={1.75} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {count < MAX_REFERENCES && (
        <div className="flex flex-col gap-3 border-t border-line pt-4">
          <TextInput
            label="Name"
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextInput
              label="Relationship"
              value={form.relationship}
              onChange={(event) => setForm({ ...form, relationship: event.target.value })}
            />
            <TextInput
              label="Phone"
              type="tel"
              value={form.phone}
              onChange={(event) => setForm({ ...form, phone: event.target.value })}
            />
          </div>
          <ErrorLine message={error} />
          <Button
            type="button"
            variant="secondary"
            fullWidthOnPhone={false}
            loading={add.isPending}
            onClick={() => add.mutate(form)}
          >
            Add reference
          </Button>
        </div>
      )}
    </Card>
  );
}

// ---------- psychology screening (CLAUDE.md section 7 step 5; the quiz itself has its own page) ----------

type PsychAttemptStatus = "in_progress" | "submitted" | "passed" | "failed";
type PsychTestSummary = { attempt: { status: PsychAttemptStatus } | null };

const PSYCH_STATUS_LABEL: Record<PsychAttemptStatus | "not_started", string> = {
  not_started: "Not started",
  in_progress: "In progress",
  submitted: "Submitted — awaiting review",
  passed: "Passed",
  failed: "Not passed — you can try again",
};

function PsychTestSection() {
  const test = useQuery({
    queryKey: ["psych-test"],
    queryFn: () => apiFetch<PsychTestSummary>("/sitter/psych-test"),
  });
  const status = test.data?.attempt?.status ?? "not_started";

  return (
    <Card as="section" className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-h3">Psychology screening</h2>
        {test.isSuccess && (
          <span className="inline-flex items-center rounded-pill bg-surface-sunken px-3 py-1 text-small text-ink">
            {PSYCH_STATUS_LABEL[status]}
          </span>
        )}
      </div>
      <p className="text-small text-muted">
        A few questions so we can get to know how you think about caring for children.
      </p>
      <ButtonLink to="/sitter/psych-test" variant="secondary" fullWidthOnPhone={false}>
        {status === "not_started" ? "Start" : status === "in_progress" ? "Continue" : "View"}
      </ButtonLink>
    </Card>
  );
}

// ---------- documents (CLAUDE.md section 7 steps 2-3; generic documents API, no new backend needed) ----------

function DocumentsSection() {
  return (
    <Card as="section" className="flex flex-col gap-5">
      <div>
        <h2 className="text-h3">Documents</h2>
        <p className="mt-1 text-small text-muted">Only Pacify admins view these, and every view is logged.</p>
      </div>
      <DocumentUpload type="government_id" label="Government ID" />
      <DocumentUpload type="college_or_work_id" label="College or work ID" />
      <DocumentUpload type="police_certificate" label="Police clearance certificate" />
      <DocumentUpload type="first_aid_certificate" label="First-aid certificate" />
    </Card>
  );
}

// ---------- the page ----------

export function SitterApplicationPage() {
  return (
    <section className="mx-auto max-w-[72rem]">
      <h1>Your application</h1>
      <p className="mt-2 text-muted">
        Tell us about yourself, add your documents and references, and set how you'd like to be paid. Your profile
        goes live once every step passes.
      </p>

      <div className="mt-7 grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <div className="flex flex-col gap-6">
          <ProfileSection />
          <DocumentsSection />
        </div>
        <div className="flex flex-col gap-6">
          <HealthDisclosureSection />
          <PayoutDetailsSection />
          <ReferencesSection />
          <PsychTestSection />
        </div>
      </div>
    </section>
  );
}
