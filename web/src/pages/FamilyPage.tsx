import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, Pencil, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useMe } from "../auth/useMe";
import { DocumentUpload, clientCheck, documentsKey, uploadOne } from "../components/documents/DocumentUpload";
import {
  BackLink,
  Button,
  ButtonLink,
  Card,
  Select,
  StepActions,
  StepBackContext,
  TextInput,
  Textarea,
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
import { formatDate, localMobile } from "../lib/format";
import { useConsent } from "./ConsentPage";
import { useChecklist, type ParentChecklist } from "./ProfileChecklist";
import { ParentProgress } from "./SitterSteps";

// ---------- shared bits ----------

type VerificationStatus = "pending" | "approved" | "rejected";

function ErrorLine({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p role="alert" className="text-small text-danger">
      {message}
    </p>
  );
}

// A fixed list instead of free text (UX review 2026-11-13). An older free-text answer stays selectable.
export const RELATIONSHIPS = ["Spouse", "Parent", "Grandparent", "Sibling", "Friend / Neighbour", "Other"];

function RelationshipSelect({
  value,
  onChange,
  error,
}: {
  value: string;
  onChange: (value: string) => void;
  error?: string;
}) {
  const options = value && !RELATIONSHIPS.includes(value) ? [value, ...RELATIONSHIPS] : RELATIONSHIPS;
  return (
    <Select label="Relationship" value={value} onChange={(event) => onChange(event.target.value)} error={error}>
      <option value="">Choose one</option>
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </Select>
  );
}

// ---------- children ----------

type Child = {
  id: string;
  name: string;
  date_of_birth: string;
  allergies: string | null;
  medical_notes: string | null;
  routines: string | null;
  verification_status: VerificationStatus;
  /** Why Pacifyco couldn't accept the birth certificate, if it was rejected. */
  rejection_reason: string | null;
  /** When Pacifyco verified the child. */
  verified_at: string | null;
};

type ChildInput = {
  name: string;
  date_of_birth: string;
  allergies: string;
  medical_notes: string;
  routines: string;
};

const EMPTY_CHILD: ChildInput = { name: "", date_of_birth: "", allergies: "", medical_notes: "", routines: "" };

function toBody(input: ChildInput) {
  return {
    name: input.name,
    date_of_birth: input.date_of_birth,
    allergies: input.allergies.trim() || null,
    medical_notes: input.medical_notes.trim() || null,
    routines: input.routines.trim() || null,
  };
}

function useChildren() {
  return useQuery({ queryKey: ["children"], queryFn: () => apiFetch<Child[]>("/parent/children") });
}

/** "4 years old", or "20 months old" under two. */
export function ageText(dateOfBirth: string, today: Date = new Date()): string {
  const born = new Date(`${dateOfBirth}T00:00:00`);
  let months = (today.getFullYear() - born.getFullYear()) * 12 + today.getMonth() - born.getMonth();
  if (today.getDate() < born.getDate()) months -= 1;
  if (months < 24) return `${Math.max(months, 0)} ${months === 1 ? "month" : "months"} old`;
  const years = Math.floor(months / 12);
  return `${years} years old`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Day, month and year selects instead of the slow native date picker (UX review 2026-11-13). */
function DateOfBirth({ value, onChange, error }: { value: string; onChange: (value: string) => void; error?: string }) {
  const [year = "", month = "", day = ""] = value ? value.split("-") : [];
  const [parts, setParts] = useState({ day, month, year });
  const thisYear = new Date().getFullYear();
  const years = Array.from({ length: 18 }, (_, index) => String(thisYear - index));

  function set(part: "day" | "month" | "year", next: string) {
    const updated = { ...parts, [part]: next };
    setParts(updated);
    onChange(updated.day && updated.month && updated.year ? `${updated.year}-${updated.month}-${updated.day}` : "");
  }

  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className="mb-2 text-ui text-ink">Date of birth</legend>
      <div className="grid grid-cols-[1fr_1.2fr_1.3fr] gap-2">
        <Select label="Day" compact value={parts.day} onChange={(event) => set("day", event.target.value)}>
          <option value="">Day</option>
          {Array.from({ length: 31 }, (_, index) => String(index + 1).padStart(2, "0")).map((d) => (
            <option key={d} value={d}>
              {Number(d)}
            </option>
          ))}
        </Select>
        <Select label="Month" compact value={parts.month} onChange={(event) => set("month", event.target.value)}>
          <option value="">Month</option>
          {MONTHS.map((name, index) => (
            <option key={name} value={String(index + 1).padStart(2, "0")}>
              {name}
            </option>
          ))}
        </Select>
        <Select label="Year" compact value={parts.year} onChange={(event) => set("year", event.target.value)}>
          <option value="">Year</option>
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </Select>
      </div>
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </fieldset>
  );
}

function ChildForm({
  initial,
  onSaved,
  onCancel,
  askCertificate = false,
}: {
  initial: ChildInput;
  onSaved: (child: ChildInput, certificate?: File) => Promise<unknown>;
  onCancel?: () => void;
  /** A new child: the birth certificate is the form's last field, sent with it (Reuben, 2026-11-13). */
  askCertificate?: boolean;
}) {
  const [form, setForm] = useState(initial);
  const [fields, setFields] = useState<FieldErrors>({});
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [certificate, setCertificate] = useState<File>();
  const certificateInput = useRef<HTMLInputElement>(null);

  function pickCertificate(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const problem = clientCheck(file, "birth_certificate");
    setFields((current) => ({ ...current, certificate: problem ?? "" }));
    setCertificate(problem ? undefined : file);
  }

  async function submit() {
    const missing: FieldErrors = {};
    if (!form.name.trim()) missing.name = "Please enter your child's name.";
    if (!form.date_of_birth) missing.date_of_birth = "Please choose the day, month and year.";
    if (askCertificate && !certificate) missing.certificate = "Please add their birth certificate.";
    setFields(missing);
    setError(undefined);
    if (Object.keys(missing).length) return;
    setBusy(true);
    try {
      await onSaved(form, certificate);
      showToast(`${form.name.trim()} saved`);
      setForm(EMPTY_CHILD);
      setCertificate(undefined);
    } catch (err) {
      const byField = fieldErrorsFrom(err);
      setFields(byField);
      setError(formErrorFrom(err, byField));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-lg bg-surface-sunken p-4 sm:p-5">
      <TextInput
        label="Child's name"
        value={form.name}
        error={fields.name}
        onChange={(event) => setForm({ ...form, name: event.target.value })}
      />
      <DateOfBirth
        value={form.date_of_birth}
        error={fields.date_of_birth}
        onChange={(value) => setForm({ ...form, date_of_birth: value })}
      />
      <TextInput
        label="Allergies"
        optional
        hint="Anything that could affect their safety, e.g. a food or medicine allergy."
        value={form.allergies}
        error={fields.allergies}
        onChange={(event) => setForm({ ...form, allergies: event.target.value })}
      />
      <Textarea
        label="Medical notes"
        optional
        hint="Include any medicine, with the dose and when to give it. Sitters only give medicine written here."
        value={form.medical_notes}
        error={fields.medical_notes}
        onChange={(event) => setForm({ ...form, medical_notes: event.target.value })}
      />
      <Textarea
        label="Routines"
        optional
        hint="Naps, meals, favourite stories — whatever helps a sitter settle in."
        value={form.routines}
        error={fields.routines}
        onChange={(event) => setForm({ ...form, routines: event.target.value })}
      />
      {askCertificate && (
        <div className="flex flex-col gap-2">
          <label htmlFor="new-child-certificate" className="text-ui text-ink">
            Birth certificate
          </label>
          <p className="-mt-1 text-small text-muted">
            PDF, JPG or PNG. Used once to check their age, then deleted — we keep only the result.
          </p>
          <input
            ref={certificateInput}
            id="new-child-certificate"
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
            className="hidden"
            onChange={pickCertificate}
          />
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              variant="secondary"
              fullWidthOnPhone={false}
              onClick={() => certificateInput.current?.click()}
            >
              <Upload aria-hidden="true" size={18} strokeWidth={1.75} />
              {certificate ? "Choose another file" : "Choose file"}
            </Button>
            {certificate && <span className="min-w-0 break-all text-small text-muted">{certificate.name}</span>}
          </div>
          <ErrorLine message={fields.certificate || undefined} />
        </div>
      )}
      <ErrorLine message={error} />
      <div className="flex flex-wrap gap-3">
        <Button type="button" loading={busy} onClick={submit}>
          Save
        </Button>
        {onCancel && (
          <Button type="button" variant="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
        )}
      </div>
    </div>
  );
}

// Where the birth certificate check stands, and why it was turned down (decided 2026-11-09).
function ChildStatus({ child }: { child: Child }) {
  if (child.verification_status === "approved") {
    return (
      <p className="flex items-center gap-2 text-small text-trust">
        <CircleCheck aria-hidden="true" size={20} strokeWidth={1.75} />
        <span>
          Verified{child.verified_at ? ` ${formatDate(new Date(child.verified_at)).replace(/ \d{4}$/, "")}` : ""}. The
          birth certificate has been deleted.
        </span>
      </p>
    );
  }
  if (child.verification_status === "rejected") {
    return (
      <div role="status" className="text-small text-danger">
        <p>Pacifyco couldn't accept this birth certificate. Please upload a new one below.</p>
        {child.rejection_reason && <p>Reason: {child.rejection_reason}</p>}
      </div>
    );
  }
  return null;
}

function ChildCard({ child }: { child: Child }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string>();

  const update = useMutation({
    mutationFn: (input: ChildInput) =>
      apiFetch<Child>(`/parent/children/${child.id}`, { method: "PUT", body: JSON.stringify(toBody(input)) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["children"] });
      setEditing(false);
    },
  });

  const remove = useMutation({
    mutationFn: () => apiFetch<void>(`/parent/children/${child.id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["children"] }),
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again."),
  });

  if (editing) {
    return (
      <ChildForm
        initial={{
          name: child.name,
          date_of_birth: child.date_of_birth,
          allergies: child.allergies ?? "",
          medical_notes: child.medical_notes ?? "",
          routines: child.routines ?? "",
        }}
        onSaved={(input) => update.mutateAsync(input)}
        onCancel={() => setEditing(false)}
      />
    );
  }

  const verified = child.verification_status === "approved";
  // A flat, bordered row rather than a card inside a card, so it keeps its width on a phone.
  return (
    <li className="flex flex-col gap-3 rounded-lg border border-line p-4 sm:p-5">
      <div>
        <h3 className="text-h3 break-words">{child.name}</h3>
        <p className="text-small text-muted">
          {ageText(child.date_of_birth)} · born {formatDate(new Date(child.date_of_birth))}
        </p>
      </div>
      {child.allergies && <p className="text-small text-ink">Allergies: {child.allergies}</p>}
      <ChildStatus child={child} />
      <ErrorLine message={error} />
      <div className="flex flex-wrap gap-4 border-t border-line pt-3">
        <Button type="button" variant="tertiary" onClick={() => setEditing(true)}>
          <Pencil aria-hidden="true" size={18} strokeWidth={1.75} />
          Edit
        </Button>
        <Button
          type="button"
          variant="tertiary"
          aria-label={`Remove ${child.name}`}
          onClick={() => remove.mutate()}
          disabled={remove.isPending}
        >
          <Trash2 aria-hidden="true" size={18} strokeWidth={1.75} />
          Remove
        </Button>
      </div>
      {/* A verified child's certificate is deleted: nothing to upload. */}
      {!verified && (
        <div className="border-t border-line pt-3">
          <DocumentUpload
            type="birth_certificate"
            childId={child.id}
            label="Birth certificate"
            hint="Used once to check their age, then deleted — we keep only the result."
          />
        </div>
      )}
    </li>
  );
}

function ChildrenSection({ onContinue }: { onContinue: () => void }) {
  const children = useChildren();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);

  // The child first, then their birth certificate, in one Save (a certificate belongs to a child).
  const add = useMutation({
    mutationFn: async ({ input, certificate }: { input: ChildInput; certificate?: File }) => {
      const child = await apiFetch<Child>("/parent/children", { method: "POST", body: JSON.stringify(toBody(input)) });
      if (certificate) {
        try {
          await uploadOne("birth_certificate", child.id, certificate);
        } catch {
          // The child is saved; the certificate can be added again from their card.
          showToast(`${child.name} saved. Please add the birth certificate again below.`);
        }
        await queryClient.invalidateQueries({ queryKey: documentsKey("birth_certificate", child.id) });
      }
      return child;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["children"] });
      setAdding(false);
    },
  });

  const none = children.isSuccess && children.data.length === 0;

  return (
    <Card as="section" padding="tight" className="flex flex-col gap-5">
      <h2 className="text-h3">Your children</h2>
      {children.isPending && <p className="text-muted">Loading…</p>}
      {none && !adding && <p className="text-muted">You haven't added a child yet.</p>}
      {children.isSuccess && children.data.length > 0 && (
        <ul className="flex flex-col gap-4">
          {children.data.map((child) => (
            <ChildCard key={child.id} child={child} />
          ))}
        </ul>
      )}
      {adding || none ? (
        <ChildForm
          initial={EMPTY_CHILD}
          askCertificate
          onSaved={(input, certificate) => add.mutateAsync({ input, certificate })}
          onCancel={none ? undefined : () => setAdding(false)}
        />
      ) : (
        <Button type="button" variant="secondary" fullWidthOnPhone={false} onClick={() => setAdding(true)}>
          Add a child
        </Button>
      )}
      <StepActions>
        <Button type="button" fullWidthOnPhone={false} onClick={onContinue} disabled={none}>
          Continue
        </Button>
      </StepActions>
      {none && <p className="-mt-3 text-small text-muted">Add a child to continue.</p>}
    </Card>
  );
}

// ---------- emergency contact (one per family, Reuben 2026-11-13) ----------

type Contact = { id: string; name: string; relationship: string; phone: string };
type ContactInput = { name: string; relationship: string; phone: string };
const EMPTY_CONTACT: ContactInput = { name: "", relationship: "", phone: "" };

function contactInput(contact: Contact | undefined): ContactInput {
  return contact
    ? { name: contact.name, relationship: contact.relationship, phone: localMobile(contact.phone) }
    : EMPTY_CONTACT;
}

/** Problems Pacifyco can spot before sending: empty fields, a wrong number, the parent's own number. */
function checkContact(contact: ContactInput, ownPhone: string | null | undefined): Partial<ContactInput> {
  const problems: Partial<ContactInput> = {};
  if (!contact.name.trim()) problems.name = "Please enter their name.";
  if (!contact.relationship) problems.relationship = "Please choose how you know them.";
  if (!isIndianMobile(contact.phone)) problems.phone = MOBILE_ERROR;
  else if (ownPhone && localMobile(contact.phone) === localMobile(ownPhone)) {
    problems.phone = "That's your own number. Please give someone else's.";
  }
  return problems;
}

function EmergencyContactSection({ onContinue }: { onContinue: () => void }) {
  const contacts = useQuery({
    queryKey: ["emergency-contacts"],
    queryFn: () => apiFetch<Contact[]>("/parent/emergency-contacts"),
  });

  return (
    <Card as="section" padding="tight" className="flex flex-col gap-5">
      <div>
        <h2 className="text-h3">Emergency contact</h2>
        <p className="mt-1 text-small text-muted">
          Someone Pacifyco can call if we can't reach you. Please get their permission before adding their details.
        </p>
      </div>
      {/* Wait for the saved contact before showing editable fields, so typing can't race the load. */}
      {contacts.isPending && <p className="text-small text-muted">Loading…</p>}
      {contacts.data && <EmergencyContactForm initial={contactInput(contacts.data[0])} onContinue={onContinue} />}
    </Card>
  );
}

function EmergencyContactForm({ initial, onContinue }: { initial: ContactInput; onContinue: () => void }) {
  const queryClient = useQueryClient();
  const me = useMe();
  const [form, setForm] = useState<ContactInput>(initial);
  const [problems, setProblems] = useState<Partial<ContactInput>>({});
  const [error, setError] = useState<string>();

  const save = useMutation({
    mutationFn: (contact: ContactInput) =>
      apiFetch<Contact[]>("/parent/emergency-contacts", {
        method: "PUT",
        body: JSON.stringify({ contacts: [contact] }),
      }),
    onSuccess: () => {
      setError(undefined);
      queryClient.invalidateQueries({ queryKey: ["emergency-contacts"] });
      showToast("Emergency contact saved");
      onContinue();
    },
    onError: (err) => {
      const byField = fieldErrorsFrom(err);
      const isYou = err instanceof ApiError && err.code === "emergency_contact_is_you";
      setProblems({
        name: byField["contacts.0.name"],
        relationship: byField["contacts.0.relationship"],
        phone: byField["contacts.0.phone"] ?? (isYou ? "That's your own number. Please give someone else's." : undefined),
      });
      setError(isYou ? undefined : (byField.contacts ?? formErrorFrom(err, byField)));
    },
  });

  function submit() {
    const found = checkContact(form, me.data?.profile?.phone);
    setProblems(found);
    setError(undefined);
    if (Object.keys(found).length) return;
    save.mutate(form);
  }

  return (
    <>
      <TextInput
        label="Name"
        value={form.name}
        error={problems.name}
        onChange={(event) => setForm({ ...form, name: event.target.value })}
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <RelationshipSelect
          value={form.relationship}
          error={problems.relationship}
          onChange={(relationship) => setForm({ ...form, relationship })}
        />
        <TextInput
          label="Mobile number"
          type="tel"
          inputMode="numeric"
          prefix="+91"
          maxLength={10}
          value={form.phone}
          error={problems.phone}
          onChange={(event) => setForm({ ...form, phone: event.target.value.replace(/\D/g, "") })}
        />
      </div>
      <ErrorLine message={error} />
      <StepActions>
        <Button type="button" fullWidthOnPhone={false} loading={save.isPending} onClick={submit}>
          Continue
        </Button>
      </StepActions>
    </>
  );
}

// ---------- the page: one step at a time (Your children, Emergency contact) ----------

const STEPS = ["children", "emergency"] as const;
type Step = (typeof STEPS)[number];

export function FamilyPage() {
  const navigate = useNavigate();
  const consent = useConsent();
  // The checklist can open a step directly, e.g. ?step=emergency.
  const [params] = useSearchParams();
  const [stepIndex, setStepIndex] = useState(() => Math.max(0, STEPS.indexOf(params.get("step") as Step)));
  const step = STEPS[stepIndex];
  const [finished, setFinished] = useState(false);

  function goNext() {
    if (stepIndex === STEPS.length - 1) {
      setFinished(true); // the last of her four steps: only the "under review" message (Reuben, 2026-11-13)
      return;
    }
    setStepIndex((index) => index + 1);
  }

  // From the first step, Back goes to "Your profile", where the form was opened.
  function goBack() {
    if (stepIndex === 0) {
      navigate("/parent/profile");
      return;
    }
    setStepIndex((index) => index - 1);
  }

  if (finished) return <ProfileInReview />;

  return (
    <article className="mx-auto max-w-[72rem]">
      <div className="mx-auto mb-4 max-w-[40rem]">
        <BackLink to="/parent/profile" label="Your profile" />
      </div>
      <div className="mx-auto max-w-[62ch] text-center">
        <h1>My family</h1>
      </div>

      <div className="mx-auto mt-7 max-w-[40rem]">
        {consent.isPending ? (
          <p className="text-center text-muted">Loading…</p>
        ) : consent.isSuccess && !consent.data.required_accepted ? (
          // Nothing about the family is saved before the consent (UX review 2026-11-13).
          <Card as="section" className="flex flex-col items-start gap-3">
            <h2 className="text-h3">Your consent comes first</h2>
            <p className="text-small text-muted">
              Before you add your children and contacts, please read and accept the parental consent form.
            </p>
            <ButtonLink to="/parent/consent" arrow>
              Read the consent form
            </ButtonLink>
          </Card>
        ) : (
          <>
            {/* The parent's four steps: this page holds the third and fourth (Reuben, 2026-11-13). */}
            <ParentProgress step={step === "children" ? "children" : "emergency_contacts"} />
            <StepBackContext.Provider value={goBack}>
              <div className="mt-4 flex flex-col gap-4">
                {step === "children" && <ChildrenSection onContinue={goNext} />}
                {step === "emergency" && <EmergencyContactSection onContinue={goNext} />}
              </div>
            </StepBackContext.Provider>
          </>
        )}
      </div>
    </article>
  );
}

/** Shown on its own once the emergency contact is saved: no heading or subheading (Reuben, 2026-11-13).
"Under review" while Pacifyco checks the birth certificates; finished once every child is verified. */
function ProfileInReview() {
  const checklist = useChecklist<ParentChecklist>("parent");
  const verified = checklist.data?.items.find((item) => item.key === "children")?.status === "approved";
  return (
    <article className="mx-auto max-w-[62ch]">
      <div role="status" className="flex flex-col items-start gap-3 rounded-lg bg-surface-sunken p-5">
        <p className="text-h3 text-ink">{verified ? "Your profile is complete." : "Your profile is under review."}</p>
        <p className="text-ink">
          {verified
            ? "You can book a sitter now."
            : "Pacifyco is checking your children's birth certificates. We'll email you once they're verified. You can find a sitter meanwhile: a booking is confirmed once the check is done."}
        </p>
        <ButtonLink to="/parent/sitters" variant="secondary">
          Find a sitter
        </ButtonLink>
      </div>
    </article>
  );
}
