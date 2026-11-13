import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { PROFILE_PATH, useMe, type Me } from "../auth/useMe";
import { BackLink, Button, LoadingScreen, TextInput, Textarea, showToast } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { localMobile } from "../lib/format";
import { areaList } from "../lib/serviceArea";

// "Your details" (CLAUDE.md 6.13): name, mobile, home pin code and address. Sign-up only asks the role
// and the terms; this is the first item of each area's "finish your profile" checklist.

type Details = { full_name: string; phone: string; pin_code: string; address: string };
type FieldErrors = Partial<Record<keyof Details, string>>;

const NAME_ERROR = "Please tell us your full name.";
const PHONE_ERROR = "That number doesn't look quite right — could you check it? We need a 10-digit mobile number.";
const ADDRESS_ERROR = "Please enter your home address.";

// Same rule as the API (app/services/accounts.py): Indian mobile, optionally with +91, 91 or 0.
export function isIndianMobile(raw: string): boolean {
  return /^(?:\+?91|0)?[6-9]\d{9}$/.test(raw.replace(/[\s\-().]/g, ""));
}

export function outsideAreaMessage(pinCode: string, pinCodes: string[] | undefined): string {
  const list = pinCodes?.length ? ` For now we're in these parts of Bengaluru: ${areaList(pinCodes)}.` : "";
  return `Pacify isn't in ${pinCode} yet.${list}`;
}

const FIELD_MESSAGES: Record<keyof Details, string> = {
  full_name: NAME_ERROR,
  phone: PHONE_ERROR,
  pin_code: "Please enter your home pin code.",
  address: ADDRESS_ERROR,
};

// The API's validation details look like [{"field": "body.phone", "message": ...}]. Use our own wording.
export function fieldErrorsFrom(details: unknown): FieldErrors {
  const errors: FieldErrors = {};
  if (!Array.isArray(details)) return errors;
  for (const detail of details) {
    const field = String((detail as { field?: unknown })?.field ?? "").split(".").pop() as keyof Details;
    if (field in FIELD_MESSAGES) errors[field] = FIELD_MESSAGES[field];
  }
  return errors;
}

// `pinCodes` is the service area from the API; if it couldn't load, the API still checks on save.
function checkDetails(details: Details, pinCodes: string[] | undefined): FieldErrors {
  const errors: FieldErrors = {};
  if (!details.full_name.trim()) errors.full_name = NAME_ERROR;
  if (!isIndianMobile(details.phone)) errors.phone = PHONE_ERROR;
  if (!/^[0-9]{6}$/.test(details.pin_code)) {
    errors.pin_code = "Pin codes have 6 digits — could you check it?";
  } else if (pinCodes && !pinCodes.includes(details.pin_code)) {
    errors.pin_code = outsideAreaMessage(details.pin_code, pinCodes);
  }
  if (!details.address.trim()) errors.address = ADDRESS_ERROR;
  return errors;
}

function DetailsForm({ initial, home, role }: { initial: Details; home: string; role: "parent" | "sitter" }) {
  const { userId } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [form, setForm] = useState(initial);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string>();
  const serviceArea = useQuery({
    queryKey: ["service-area"],
    queryFn: () => apiFetch<{ pin_codes: string[] }>("/service-area"),
    staleTime: 60 * 60 * 1000,
  });

  const save = useMutation({
    mutationFn: (body: Details) => apiFetch<Me>("/me/details", { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: async (me) => {
      queryClient.setQueryData(["me", userId], me);
      await queryClient.invalidateQueries({ queryKey: ["checklist"] });
      showToast("Details saved"); // stays up on the page they go back to (UX review 2026-11-13)
      navigate(home);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "outside_service_area") {
        setFieldErrors({ pin_code: outsideAreaMessage(form.pin_code, serviceArea.data?.pin_codes) });
      } else if (error instanceof ApiError && error.code === "validation_error") {
        const errors = fieldErrorsFrom(error.details);
        setFieldErrors(errors);
        if (!Object.keys(errors).length) setFormError("Something didn't go through. Please reload the page and try again.");
      } else {
        setFormError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
      }
    },
  });

  function set(field: keyof Details, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  // The pin codes Pacify serves, up front, so nobody types one only to be turned away.
  const served = serviceArea.data?.pin_codes;
  const pinHint =
    role === "sitter"
      ? `Where you live. We're matching sitters with families in ${served?.length ? areaList(served) : "a few Bengaluru neighbourhoods"}.`
      : served?.length
        ? `For now Pacify is in ${areaList(served)}.`
        : "Pacify is starting in a few Bengaluru neighbourhoods.";

  function submit(event: FormEvent) {
    event.preventDefault();
    const errors = checkDetails(form, serviceArea.data?.pin_codes);
    setFieldErrors(errors);
    setFormError(undefined);
    if (Object.keys(errors).length === 0) {
      save.mutate({
        full_name: form.full_name.trim(),
        phone: form.phone.trim(),
        pin_code: form.pin_code,
        address: form.address.trim(),
      });
    }
  }

  return (
    <form onSubmit={submit} className="mt-6 flex flex-col gap-5 text-left" noValidate>
      {formError && (
        <p role="alert" className="text-small text-danger">
          {formError}
        </p>
      )}
      <TextInput
        label="Full name"
        name="full_name"
        autoComplete="name"
        maxLength={100}
        value={form.full_name}
        onChange={(event) => set("full_name", event.target.value)}
        error={fieldErrors.full_name}
      />
      <TextInput
        label="Mobile number"
        name="phone"
        type="tel"
        autoComplete="tel-national"
        inputMode="numeric"
        prefix="+91"
        maxLength={10}
        hint={
          role === "sitter"
            ? "Pacify uses it to reach you about your work."
            : "Pacify uses it to reach you about your bookings."
        }
        value={form.phone}
        onChange={(event) => set("phone", event.target.value.replace(/\D/g, ""))}
        error={fieldErrors.phone}
      />
      <TextInput
        label="Home pin code"
        name="pin_code"
        autoComplete="postal-code"
        inputMode="numeric"
        maxLength={6}
        hint={pinHint}
        value={form.pin_code}
        onChange={(event) => set("pin_code", event.target.value.replace(/\D/g, ""))}
        error={fieldErrors.pin_code}
      />
      <Textarea
        label="Home address"
        name="address"
        autoComplete="street-address"
        maxLength={300}
        rows={3}
        hint="House or flat number, street and area."
        value={form.address}
        onChange={(event) => set("address", event.target.value)}
        error={fieldErrors.address}
      />
      <Button type="submit" arrow loading={save.isPending} fullWidthOnPhone={false} className="w-full">
        Save my details
      </Button>
    </form>
  );
}

export function DetailsPage() {
  const { name } = useAuth();
  const me = useMe();
  if (me.isPending) return <LoadingScreen />;
  if (me.isError || !me.data.profile) return <p className="text-center text-muted">Please reload the page.</p>;

  const profile = me.data.profile;
  const initial: Details = {
    full_name: profile.full_name ?? name ?? "", // Google's name, if they signed in with Google
    phone: localMobile(profile.phone), // the field shows +91 itself
    pin_code: profile.pin_code ?? "",
    address: profile.address ?? "",
  };
  return (
    <section className="mx-auto max-w-[28rem] text-center">
      <div className="mb-4 text-left">
        <BackLink to={PROFILE_PATH[profile.role as "parent" | "sitter"]} label="Your profile" />
      </div>
      <h1>Your details.</h1>
      <p className="mt-4 text-muted">
        {profile.role === "parent"
          ? "So your sitter knows where to come, and Pacify can reach you."
          : "So Pacify can reach you about your work."}
      </p>
      <DetailsForm
        initial={initial}
        role={profile.role as "parent" | "sitter"}
        home={PROFILE_PATH[profile.role as "parent" | "sitter"]}
      />
    </section>
  );
}
