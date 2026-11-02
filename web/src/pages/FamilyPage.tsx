import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { DocumentUpload, DocumentUploadList } from "../components/documents/DocumentUpload";
import { Button, Card, Checkbox, TextInput, Textarea } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { formatDate } from "../lib/format";

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

// ---------- children ----------

type Child = {
  id: string;
  name: string;
  date_of_birth: string;
  allergies: string | null;
  medical_notes: string | null;
  routines: string | null;
  verification_status: VerificationStatus;
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

function ChildForm({
  initial,
  onSaved,
  onCancel,
}: {
  initial: ChildInput;
  onSaved: (child: ChildInput) => Promise<unknown>;
  onCancel?: () => void;
}) {
  const [form, setForm] = useState(initial);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(undefined);
    try {
      await onSaved(form);
      setForm(EMPTY_CHILD);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 rounded-lg bg-surface-sunken p-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <TextInput
          label="Child's name"
          value={form.name}
          onChange={(event) => setForm({ ...form, name: event.target.value })}
        />
        <TextInput
          label="Date of birth"
          type="date"
          value={form.date_of_birth}
          onChange={(event) => setForm({ ...form, date_of_birth: event.target.value })}
        />
      </div>
      <TextInput
        label="Allergies"
        optional
        hint="Anything that could affect their safety, e.g. a food or medicine allergy."
        value={form.allergies}
        onChange={(event) => setForm({ ...form, allergies: event.target.value })}
      />
      <Textarea
        label="Medical notes"
        optional
        value={form.medical_notes}
        onChange={(event) => setForm({ ...form, medical_notes: event.target.value })}
      />
      <Textarea
        label="Routines"
        optional
        hint="Naps, meals, favourite stories — whatever helps a sitter settle in."
        value={form.routines}
        onChange={(event) => setForm({ ...form, routines: event.target.value })}
      />
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

  return (
    <Card as="li" className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-h3">{child.name}</h3>
          <p className="text-small text-muted">Born {formatDate(new Date(child.date_of_birth))}</p>
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="tertiary" onClick={() => setEditing(true)}>
            Edit
          </Button>
          <button
            type="button"
            aria-label={`Remove ${child.name}`}
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
            className="inline-flex size-9 items-center justify-center rounded-pill text-muted hover:bg-surface-sunken hover:text-danger disabled:opacity-50"
          >
            <Trash2 aria-hidden="true" size={18} strokeWidth={1.75} />
          </button>
        </div>
      </div>
      {child.allergies && <p className="text-small text-ink">Allergies: {child.allergies}</p>}
      <ErrorLine message={error} />
      <div className="border-t border-line pt-3">
        <DocumentUpload
          type="birth_certificate"
          childId={child.id}
          label="Birth certificate"
          hint="Used once to check their age, then deleted — we keep only the result."
        />
      </div>
    </Card>
  );
}

function ChildrenSection() {
  const children = useChildren();
  const queryClient = useQueryClient();
  const [adding, setAdding] = useState(false);

  const add = useMutation({
    mutationFn: (input: ChildInput) =>
      apiFetch<Child>("/parent/children", { method: "POST", body: JSON.stringify(toBody(input)) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["children"] });
      setAdding(false);
    },
  });

  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-5">
      <h2 className="text-h3">Your children</h2>
      {children.isPending && <p className="text-muted">Loading…</p>}
      {children.isSuccess && children.data.length === 0 && !adding && (
        <p className="text-muted">You haven't added a child yet.</p>
      )}
      {children.isSuccess && children.data.length > 0 && (
        <ul className="flex flex-col gap-4">
          {children.data.map((child) => (
            <ChildCard key={child.id} child={child} />
          ))}
        </ul>
      )}
      {adding ? (
        <ChildForm initial={EMPTY_CHILD} onSaved={(input) => add.mutateAsync(input)} onCancel={() => setAdding(false)} />
      ) : (
        <Button type="button" variant="secondary" fullWidthOnPhone={false} onClick={() => setAdding(true)}>
          Add a child
        </Button>
      )}
    </Card>
  );
}

// ---------- emergency contacts ----------

type Contact = { id: string; name: string; relationship: string; phone: string };
type ContactInput = { name: string; relationship: string; phone: string };
const EMPTY_CONTACT: ContactInput = { name: "", relationship: "", phone: "" };

function contactInput(contact: Contact | undefined): ContactInput {
  return contact ? { name: contact.name, relationship: contact.relationship, phone: contact.phone } : EMPTY_CONTACT;
}

function EmergencyContactsSection() {
  const contacts = useQuery({
    queryKey: ["emergency-contacts"],
    queryFn: () => apiFetch<Contact[]>("/parent/emergency-contacts"),
  });

  return (
    <Card as="section" className="flex flex-col gap-5">
      <div>
        <h2 className="text-h3">Emergency contacts</h2>
        <p className="mt-1 text-small text-muted">
          Two people Pacify can reach if you and your authorised adults can't be. Please get their permission before
          adding their details.
        </p>
      </div>
      {/* Wait for the server's contacts before showing editable fields at all: mounting the form only
      once, seeded from real data, means there's never a window where typing can race a background
      load and get overwritten. */}
      {contacts.isPending && <p className="text-small text-muted">Loading…</p>}
      {contacts.data && (
        <EmergencyContactsForm initial={[contactInput(contacts.data[0]), contactInput(contacts.data[1])]} />
      )}
    </Card>
  );
}

function EmergencyContactsForm({ initial }: { initial: [ContactInput, ContactInput] }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<[ContactInput, ContactInput]>(initial);
  const [error, setError] = useState<string>();

  const save = useMutation({
    mutationFn: (pair: [ContactInput, ContactInput]) =>
      apiFetch<Contact[]>("/parent/emergency-contacts", { method: "PUT", body: JSON.stringify({ contacts: pair }) }),
    onSuccess: () => {
      setError(undefined);
      queryClient.invalidateQueries({ queryKey: ["emergency-contacts"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again."),
  });

  function setAt(index: 0 | 1, patch: Partial<ContactInput>) {
    const next = [...form] as [ContactInput, ContactInput];
    next[index] = { ...next[index], ...patch };
    setForm(next);
  }

  return (
    <>
      {([0, 1] as const).map((index) => (
        <div key={index} className="flex flex-col gap-3 border-t border-line pt-4 first:border-t-0 first:pt-0">
          <p className="text-eyebrow text-muted uppercase">Contact {index + 1}</p>
          <TextInput
            label="Name"
            value={form[index].name}
            onChange={(event) => setAt(index, { name: event.target.value })}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextInput
              label="Relationship"
              value={form[index].relationship}
              onChange={(event) => setAt(index, { relationship: event.target.value })}
            />
            <TextInput
              label="Phone"
              type="tel"
              value={form[index].phone}
              onChange={(event) => setAt(index, { phone: event.target.value })}
            />
          </div>
        </div>
      ))}
      <ErrorLine message={error} />
      <Button type="button" fullWidthOnPhone={false} loading={save.isPending} onClick={() => save.mutate(form)}>
        Save contacts
      </Button>
    </>
  );
}

// ---------- authorised adults ----------

function AuthorisedAdultsSection() {
  const queryClient = useQueryClient();
  const adults = useQuery({
    queryKey: ["authorised-adults"],
    queryFn: () => apiFetch<Contact[]>("/parent/authorised-adults"),
  });
  const [form, setForm] = useState<ContactInput>(EMPTY_CONTACT);
  const [error, setError] = useState<string>();

  const add = useMutation({
    mutationFn: (input: ContactInput) =>
      apiFetch<Contact>("/parent/authorised-adults", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["authorised-adults"] });
      setForm(EMPTY_CONTACT);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again."),
  });

  const remove = useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/parent/authorised-adults/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["authorised-adults"] }),
  });

  return (
    <Card as="section" className="flex flex-col gap-5">
      <div>
        <h2 className="text-h3">Authorised adults</h2>
        <p className="mt-1 text-small text-muted">
          Anyone else who may hand over or receive your child during a booking. Please get their permission first.
        </p>
      </div>
      {adults.isSuccess && adults.data.length > 0 && (
        <ul className="flex flex-col gap-2">
          {adults.data.map((adult) => (
            <li key={adult.id} className="flex items-center gap-3 rounded-md bg-surface-sunken px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-ui text-ink">{adult.name}</p>
                <p className="text-small text-muted">
                  {adult.relationship} · {adult.phone}
                </p>
              </div>
              <button
                type="button"
                aria-label={`Remove ${adult.name}`}
                onClick={() => remove.mutate(adult.id)}
                className="inline-flex size-9 shrink-0 items-center justify-center rounded-pill text-muted hover:text-danger"
              >
                <Trash2 aria-hidden="true" size={18} strokeWidth={1.75} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-col gap-3 border-t border-line pt-4">
        <TextInput label="Name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
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
        <Button type="button" variant="secondary" fullWidthOnPhone={false} loading={add.isPending} onClick={() => add.mutate(form)}>
          Add
        </Button>
      </div>
    </Card>
  );
}

// ---------- masked Aadhaar and single-parent declaration ----------

function AadhaarSection() {
  const queryClient = useQueryClient();
  const declaration = useQuery({
    queryKey: ["single-parent-declaration"],
    queryFn: () => apiFetch<{ declared: boolean }>("/parent/single-parent-declaration"),
  });

  const setDeclared = useMutation({
    mutationFn: (declared: boolean) =>
      apiFetch<{ declared: boolean }>("/parent/single-parent-declaration", {
        method: "PATCH",
        body: JSON.stringify({ declared }),
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["single-parent-declaration"] }),
  });

  return (
    <Card as="section" className="flex flex-col gap-5">
      <div>
        <h2 className="text-h3">Masked Aadhaar</h2>
        <p className="mt-1 text-small text-muted">
          Both parents' masked Aadhaar (the copy with most digits hidden, as UIDAI issues it). Only Pacify admins
          view it, and we delete each copy once it's approved.
        </p>
      </div>
      <DocumentUploadList type="aadhaar_masked" label="Masked Aadhaar" max={2} />
      <div className="border-t border-line pt-4">
        <Checkbox
          label="I'm the only parent or legal guardian of the children I add."
          checked={declaration.data?.declared ?? false}
          onChange={(event) => setDeclared.mutate(event.target.checked)}
        />
      </div>
    </Card>
  );
}

// ---------- the page ----------

export function FamilyPage() {
  return (
    <section className="mx-auto max-w-[72rem]">
      <h1>My family</h1>
      <p className="mt-2 text-muted">
        Add your children, two emergency contacts and anyone else authorised to hand over or receive them, and the
        masked Aadhaar for both parents (or a declaration if you're their only parent or guardian).
      </p>

      <div className="mt-7 grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <ChildrenSection />
        <div className="flex flex-col gap-6">
          <EmergencyContactsSection />
          <AuthorisedAdultsSection />
          <AadhaarSection />
        </div>
      </div>
    </section>
  );
}
