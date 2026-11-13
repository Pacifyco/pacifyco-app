import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useMe } from "../auth/useMe";
import { DocumentUpload, useMyDocuments, type DocumentType } from "../components/documents/DocumentUpload";
import {
  BackLink,
  Button,
  Card,
  Checkbox,
  Select,
  StepActions,
  StepBackContext,
  TextInput,
  Textarea,
  ToggleChip,
  showToast,
} from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import {
  MOBILE_ERROR,
  fieldErrorsFrom,
  formErrorFrom,
  isIndianMobile,
  type FieldErrors,
} from "../lib/fieldErrors";
import { formatMobile, localMobile } from "../lib/format";
import { AGE_GROUPS, LANGUAGES } from "../lib/sitterLists";
import { firstToDo, useChecklist, type SitterChecklist } from "./ProfileChecklist";
import { SitterGate, SitterProgress } from "./SitterSteps";

// ---------- shared bits ----------

function ErrorLine({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p role="alert" className="text-small text-danger">
      {message}
    </p>
  );
}

/** Tap to pick, from a fixed list (UX review 2026-11-13: free text showed parents typos). */
function ChipPicker({
  label,
  hint,
  options,
  value,
  onChange,
  error,
}: {
  label: string;
  hint?: string;
  options: readonly { value: string; label: string }[];
  value: string[];
  onChange: (value: string[]) => void;
  error?: string;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-ui text-ink">{label}</legend>
      {hint && <p className="text-small text-muted">{hint}</p>}
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const on = value.includes(option.value);
          return (
            <ToggleChip
              key={option.value}
              mark="tick"
              on={on}
              onToggle={() => onChange(on ? value.filter((item) => item !== option.value) : [...value, option.value])}
            >
              {option.label}
            </ToggleChip>
          );
        })}
      </div>
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </fieldset>
  );
}

const AGE_OPTIONS = AGE_GROUPS.map((group) => ({ value: group.name, label: group.label }));
const LANGUAGE_OPTIONS = LANGUAGES.map((language) => ({ value: language, label: language }));

// ---------- profile (CLAUDE.md section 7 step 1) ----------

type OnboardingStatus = "in_progress" | "approved" | "rejected";

type SitterProfile = {
  date_of_birth: string | null;
  bio: string | null;
  years_experience: number | null;
  age_groups: string[];
  languages: string[];
  first_aid: boolean;
  reference_shared_consent: boolean;
  onboarding_status: OnboardingStatus;
};

type ProfileInput = {
  date_of_birth: string;
  bio: string;
  years_experience: string;
  age_groups: string[];
  languages: string[];
  first_aid: boolean;
  reference_shared_consent: boolean;
};

function profileInput(profile: SitterProfile): ProfileInput {
  return {
    date_of_birth: profile.date_of_birth ?? "",
    bio: profile.bio ?? "",
    years_experience: profile.years_experience !== null ? String(profile.years_experience) : "",
    age_groups: profile.age_groups,
    languages: profile.languages,
    first_aid: profile.first_aid,
    reference_shared_consent: profile.reference_shared_consent,
  };
}

function toProfileBody(input: ProfileInput) {
  return {
    date_of_birth: input.date_of_birth,
    bio: input.bio.trim() || null,
    years_experience: Number(input.years_experience),
    age_groups: input.age_groups,
    languages: input.languages,
    first_aid: input.first_aid,
    reference_shared_consent: input.reference_shared_consent,
  };
}

/** What the form can check before sending: everything parents need to see is required. */
function checkProfile(input: ProfileInput): FieldErrors {
  const errors: FieldErrors = {};
  if (!input.date_of_birth) errors.date_of_birth = "Please enter your date of birth.";
  if (input.years_experience === "") errors.years_experience = "Please enter your years of experience (0 is fine).";
  if (!input.bio.trim()) errors.bio = "Please write a few words for parents.";
  if (!input.age_groups.length) errors.age_groups = "Please choose at least one age group.";
  if (!input.languages.length) errors.languages = "Please choose at least one language.";
  return errors;
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

function ProfileForm({
  initial,
  status,
  onContinue,
}: {
  initial: ProfileInput;
  status: OnboardingStatus;
  onContinue: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(initial);
  const [fields, setFields] = useState<FieldErrors>({});
  const [error, setError] = useState<string>();
  const photo = useMyDocuments("photo");
  const hasPhoto = !!photo.data?.some((document) => document.status === "uploaded");

  const save = useMutation({
    mutationFn: () =>
      apiFetch<SitterProfile>("/sitter/profile", { method: "PUT", body: JSON.stringify(toProfileBody(form)) }),
    onSuccess: () => {
      setError(undefined);
      queryClient.invalidateQueries({ queryKey: ["sitter-profile"] });
      showToast("Profile saved");
      onContinue();
    },
    onError: (err) => {
      const byField = fieldErrorsFrom(err);
      setFields(byField);
      setError(formErrorFrom(err, byField));
    },
  });

  function submit() {
    const found = checkProfile(form);
    if (!hasPhoto) found.photo = "Please add your photo.";
    setFields(found);
    setError(undefined);
    if (!Object.keys(found).length) save.mutate();
  }

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
          error={fields.date_of_birth}
          onChange={(event) => setForm({ ...form, date_of_birth: event.target.value })}
        />
        <TextInput
          label="Years of experience"
          type="number"
          min={0}
          max={80}
          value={form.years_experience}
          error={fields.years_experience}
          onChange={(event) => setForm({ ...form, years_experience: event.target.value })}
        />
      </div>
      <Textarea
        label="About you"
        hint="What parents see first. Try: how long you've cared for children, what you love doing with them, and anything families should know."
        placeholder="I've looked after my nieces since they were babies. I love storytime, drawing and being outdoors…"
        value={form.bio}
        error={fields.bio}
        onChange={(event) => setForm({ ...form, bio: event.target.value })}
      />
      <ChipPicker
        label="Age groups you care for"
        hint="Pacifyco looks after children from 18 months."
        options={AGE_OPTIONS}
        value={form.age_groups}
        error={fields.age_groups}
        onChange={(age_groups) => setForm({ ...form, age_groups })}
      />
      <ChipPicker
        label="Languages you speak"
        options={LANGUAGE_OPTIONS}
        value={form.languages}
        error={fields.languages}
        onChange={(languages) => setForm({ ...form, languages })}
      />
      <Checkbox
        label="I'm first-aid certified"
        checked={form.first_aid}
        onChange={(event) => setForm({ ...form, first_aid: event.target.checked })}
      />
      <DocumentUpload
        type="photo"
        label="Profile photo"
        hint="Parents see it once your profile is live. JPG or PNG. Your face clearly, in good light, on a plain background. No sunglasses, pets or other people in front of you."
      />
      <ErrorLine message={fields.photo} />
      <ErrorLine message={error} />
      <StepActions>
        <Button type="button" fullWidthOnPhone={false} loading={save.isPending} onClick={submit}>
          Continue
        </Button>
      </StepActions>
    </>
  );
}

function ProfileSection({ onContinue }: { onContinue: () => void }) {
  const profile = useSitterProfile();
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-5">
      {profile.isPending && <p className="text-muted">Loading…</p>}
      {profile.data && (
        <ProfileForm
          initial={profileInput(profile.data)}
          status={profile.data.onboarding_status}
          onContinue={onContinue}
        />
      )}
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

function HealthDisclosureForm({ initial, onContinue }: { initial: string; onContinue: () => void }) {
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
      showToast("Health disclosure saved");
      onContinue();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again."),
  });

  return (
    <>
      <Textarea
        label="Health disclosure"
        optional
        hint="Any serious or long-term condition or allergy that could affect safe care. Only Pacifyco admins can see this — never shown to parents, and used only to match you safely."
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
      <ErrorLine message={error} />
      <StepActions>
        <Button type="button" fullWidthOnPhone={false} loading={save.isPending} onClick={() => save.mutate()}>
          Continue
        </Button>
      </StepActions>
    </>
  );
}

function HealthDisclosureSection({ onContinue }: { onContinue: () => void }) {
  const disclosure = useHealthDisclosure();
  return (
    <Card as="section" className="flex flex-col gap-5">
      <h2 className="text-h3">Health disclosure</h2>
      {disclosure.isPending && <p className="text-small text-muted">Loading…</p>}
      {disclosure.data && <HealthDisclosureForm initial={disclosure.data.disclosure ?? ""} onContinue={onContinue} />}
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

function PayoutDetailsForm({ initial, onContinue }: { initial: PayoutInput; onContinue: () => void }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(initial);
  const [fields, setFields] = useState<FieldErrors>({});
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
      showToast("Payout details saved");
      onContinue();
    },
    onError: (err) => {
      const byField = fieldErrorsFrom(err);
      setFields(byField);
      setError(formErrorFrom(err, byField));
    },
  });

  function submit() {
    const found: FieldErrors = {};
    if (form.method === "bank") {
      if (!form.account_holder_name.trim()) found.account_holder_name = "Please enter the account holder's name.";
      if (!/^\d{6,18}$/.test(form.account_number.trim())) found.account_number = "Please enter the account number.";
      if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(form.ifsc_code.trim())) found.ifsc_code = "Please enter the 11-character IFSC code.";
    } else if (!/^[\w.-]+@[\w.-]+$/.test(form.upi_id.trim())) {
      found.upi_id = "Please enter your UPI ID, like name@okbank.";
    }
    setFields(found);
    setError(undefined);
    if (!Object.keys(found).length) save.mutate();
  }

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
            error={fields.account_holder_name}
            onChange={(event) => setForm({ ...form, account_holder_name: event.target.value })}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextInput
              label="Account number"
              value={form.account_number}
              error={fields.account_number}
              onChange={(event) => setForm({ ...form, account_number: event.target.value })}
            />
            <TextInput
              label="IFSC code"
              value={form.ifsc_code}
              error={fields.ifsc_code}
              onChange={(event) => setForm({ ...form, ifsc_code: event.target.value.toUpperCase() })}
            />
          </div>
        </>
      ) : (
        <TextInput
          label="UPI ID"
          hint="Like name@okbank."
          value={form.upi_id}
          error={fields.upi_id}
          onChange={(event) => setForm({ ...form, upi_id: event.target.value })}
        />
      )}
      <ErrorLine message={error} />
      <StepActions>
        <Button type="button" fullWidthOnPhone={false} loading={save.isPending} onClick={submit}>
          Continue to the psychology screening
        </Button>
      </StepActions>
    </>
  );
}

function PayoutDetailsSection({ onContinue }: { onContinue: () => void }) {
  const details = usePayoutDetails();
  return (
    <Card as="section" className="flex flex-col gap-5">
      <div>
        <h2 className="text-h3">Payment details</h2>
        <p className="mt-1 text-small text-muted">How Pacifyco pays you, within 12 hours of each booking.</p>
      </div>
      {details.isPending && <p className="text-small text-muted">Loading…</p>}
      {details.data && <PayoutDetailsForm initial={payoutInput(details.data)} onContinue={onContinue} />}
    </Card>
  );
}

// ---------- references (CLAUDE.md section 7 step 4) ----------

type ReferenceOutcome = "pending" | "approved" | "rejected";
type Reference = {
  id: string;
  name: string;
  relationship: string;
  phone: string;
  outcome: ReferenceOutcome;
  /** Why Pacifyco couldn't accept it, if it was rejected. */
  rejection_reason: string | null;
};
type ReferenceInput = { name: string; relationship: string; phone: string };
const EMPTY_REFERENCE: ReferenceInput = { name: "", relationship: "", phone: "" };
const MAX_REFERENCES = 1; // one, and optional but good to have (Reuben, 2026-11-13)

const REFERENCE_NUMBER_MESSAGES = {
  reference_is_you: "That's your own number. Please give your reference's.",
  reference_number_used: "You've already given that number. Please give a different one.",
};

function ReferencesSection({ onContinue }: { onContinue: () => void }) {
  const queryClient = useQueryClient();
  const me = useMe();
  const references = useQuery({ queryKey: ["references"], queryFn: () => apiFetch<Reference[]>("/sitter/references") });
  const [form, setForm] = useState<ReferenceInput>(EMPTY_REFERENCE);
  const [fields, setFields] = useState<FieldErrors>({});
  const [error, setError] = useState<string>();

  // Every problem is shown under its own field (UX review 2026-11-13: "Some fields need fixing" alone
  // didn't say which).
  const add = useMutation({
    mutationFn: (input: ReferenceInput) =>
      apiFetch<Reference>("/sitter/references", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: (reference) => {
      queryClient.invalidateQueries({ queryKey: ["references"] });
      setForm(EMPTY_REFERENCE);
      setFields({});
      setError(undefined);
      showToast(`${reference.name} added`);
    },
    onError: (err) => {
      // Her own number, or one she has given before: shown on the number field.
      if (err instanceof ApiError && (err.code === "reference_is_you" || err.code === "reference_number_used")) {
        setFields({ phone: REFERENCE_NUMBER_MESSAGES[err.code] });
        setError(undefined);
        return;
      }
      const byField = fieldErrorsFrom(err);
      setFields(byField);
      setError(formErrorFrom(err, byField));
    },
  });

  function submit() {
    const found: FieldErrors = {};
    if (!form.name.trim()) found.name = "Please enter their name.";
    if (!form.relationship.trim()) found.relationship = "Please say how they know you, e.g. Former employer.";
    if (!isIndianMobile(form.phone)) found.phone = MOBILE_ERROR;
    else if (me.data?.profile?.phone && localMobile(form.phone) === localMobile(me.data.profile.phone)) {
      found.phone = REFERENCE_NUMBER_MESSAGES.reference_is_you;
    } else if ((references.data ?? []).some((reference) => localMobile(reference.phone) === localMobile(form.phone))) {
      found.phone = REFERENCE_NUMBER_MESSAGES.reference_number_used;
    }
    setFields(found);
    setError(undefined);
    if (!Object.keys(found).length) add.mutate(form);
  }

  const remove = useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/sitter/references/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["references"] }),
  });

  const count = references.data?.length ?? 0;
  const [continueError, setContinueError] = useState<string>();

  // Optional: she can continue without one.
  function next() {
    setContinueError(undefined);
    onContinue();
  }

  return (
    <Card as="section" className="flex flex-col gap-5">
      <div>
        <h2 className="text-h3">References</h2>
        <p className="mt-1 text-small text-muted">
          1 person who can vouch for you. Optional, but it helps families trust you. Pacifyco will contact them.
        </p>
      </div>
      {references.isSuccess && references.data.length > 0 && (
        <ul className="flex flex-col gap-2">
          {references.data.map((reference) => (
            <li key={reference.id} className="flex items-center gap-3 rounded-md bg-surface-sunken px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-ui text-ink">{reference.name}</p>
                <p className="text-small text-muted">
                  {reference.relationship} · {formatMobile(reference.phone)}
                </p>
                {reference.outcome === "rejected" && (
                  <div className="mt-1 text-small text-danger">
                    <p>Pacifyco couldn't accept this reference. Please remove it and add someone else.</p>
                    {reference.rejection_reason && <p>Reason: {reference.rejection_reason}</p>}
                  </div>
                )}
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
            error={fields.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextInput
              label="Relationship"
              hint="e.g. Former employer, Neighbour"
              value={form.relationship}
              error={fields.relationship}
              onChange={(event) => setForm({ ...form, relationship: event.target.value })}
            />
            <TextInput
              label="Mobile number"
              type="tel"
              inputMode="numeric"
              prefix="+91"
              maxLength={10}
              value={form.phone}
              error={fields.phone}
              onChange={(event) => setForm({ ...form, phone: event.target.value.replace(/\D/g, "") })}
            />
          </div>
          <ErrorLine message={error} />
          <Button type="button" variant="secondary" fullWidthOnPhone={false} loading={add.isPending} onClick={submit}>
            Add this reference
          </Button>
        </div>
      )}
      <ErrorLine message={continueError} />
      <StepActions>
        <Button type="button" fullWidthOnPhone={false} onClick={next}>
          Continue
        </Button>
      </StepActions>
    </Card>
  );
}

// ---------- documents (CLAUDE.md section 7 steps 2-3; generic documents API, no new backend needed) ----------

function useUploaded(type: DocumentType) {
  const documents = useMyDocuments(type);
  return !!documents.data?.some((document) => document.status === "uploaded");
}

function DocumentsSection({ onContinue }: { onContinue: () => void }) {
  const profile = useSitterProfile();
  const firstAid = !!profile.data?.first_aid;
  const government = useUploaded("government_id");
  const collegeOrWork = useUploaded("college_or_work_id");
  const firstAidCertificate = useUploaded("first_aid_certificate");
  const [error, setError] = useState<string>();

  function next() {
    const missing = [
      !government && "your government ID",
      !collegeOrWork && "a college or work ID",
      firstAid && !firstAidCertificate && "your first-aid certificate",
    ].filter(Boolean);
    if (missing.length) return setError(`Please add ${missing.join(" and ")} to continue.`);
    setError(undefined);
    onContinue();
  }

  return (
    <Card as="section" className="flex flex-col gap-5">
      <div>
        <h2 className="text-h3">ID verification</h2>
        <p className="mt-1 text-small text-muted">Only Pacifyco admins view these, and every view is logged.</p>
      </div>
      <DocumentUpload type="government_id" label="Government ID" />
      <DocumentUpload type="college_or_work_id" label="College or work ID" />
      {firstAid && (
        <DocumentUpload
          type="first_aid_certificate"
          label="First-aid certificate"
          hint="You said you're first-aid certified."
        />
      )}
      <DocumentUpload
        type="police_certificate"
        label="Police clearance certificate (optional for now)"
        hint="You can add it later, but Pacifyco needs it before your profile goes live."
      />
      <ErrorLine message={error} />
      <StepActions>
        <Button type="button" fullWidthOnPhone={false} onClick={next}>
          Continue
        </Button>
      </StepActions>
    </Card>
  );
}

// ---------- the page: one step at a time (About you, Documents, Health disclosure, References, ----------
// ---------- Payout details), ending at the psychology screening page ----------

const STEPS = ["profile", "documents", "health", "references", "payout"] as const;
type Step = (typeof STEPS)[number];
/** Each part of this page is one of her eight onboarding steps (Reuben, 2026-11-13). */
const CHECKLIST_KEY: Record<Step, string> = {
  profile: "profile",
  documents: "identity_documents",
  health: "health_disclosure",
  references: "references",
  payout: "payout",
};

export function SitterApplicationPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const checklist = useChecklist<SitterChecklist>("sitter");
  // The checklist opens the exact step to finish, e.g. ?step=references (UX review 2026-11-13). Without
  // one, she starts at the first step still to do.
  const [params] = useSearchParams();
  const asked = STEPS.indexOf(params.get("step") as Step);
  const open = checklist.isSuccess ? firstToDo(checklist.data.items) : null;
  const firstOpen = Math.max(0, STEPS.findIndex((item) => CHECKLIST_KEY[item] === open));
  // Null until she moves on or back; until then, the step asked for or the first one still to do.
  const [moved, setStepIndex] = useState<number | null>(null);
  const stepIndex = moved ?? (asked >= 0 ? asked : firstOpen);
  const step = STEPS[stepIndex];

  async function goNext() {
    // The next step opens once this one counts as done, so refresh where she stands first.
    await queryClient.invalidateQueries({ queryKey: ["checklist"] });
    if (stepIndex === STEPS.length - 1) {
      navigate("/sitter/psych-test"); // the next onboarding step, on its own page
      return;
    }
    setStepIndex(stepIndex + 1);
  }

  // From the first step, Back goes to "Your profile", where the form was opened.
  function goBack() {
    if (stepIndex === 0) {
      navigate("/sitter/profile");
      return;
    }
    setStepIndex(stepIndex - 1);
  }

  return (
    <article className="mx-auto max-w-[72rem]">
      <div className="mx-auto mb-4 max-w-[40rem]">
        <BackLink to="/sitter/profile" label="Your profile" />
      </div>
      <div className="mx-auto max-w-[62ch] text-center">
        <h1>Your application</h1>
        <p className="mt-2 text-muted">
          Tell us about yourself, add your documents and references, and set how you'd like to be paid. Your profile
          goes live once every step passes.
        </p>
      </div>

      <div className="mx-auto mt-7 max-w-[40rem]">
        <SitterProgress step={CHECKLIST_KEY[step]} />
        <StepBackContext.Provider value={goBack}>
          <div className="mt-4 flex flex-col gap-4">
            {/* Steps open in order: an earlier step still to do (the consent too) is shown instead. */}
            <SitterGate step={CHECKLIST_KEY[step]}>
              {step === "profile" && <ProfileSection onContinue={goNext} />}
              {step === "documents" && <DocumentsSection onContinue={goNext} />}
              {step === "health" && <HealthDisclosureSection onContinue={goNext} />}
              {step === "references" && <ReferencesSection onContinue={goNext} />}
              {step === "payout" && <PayoutDetailsSection onContinue={goNext} />}
            </SitterGate>
          </div>
        </StepBackContext.Provider>
      </div>
    </article>
  );
}
