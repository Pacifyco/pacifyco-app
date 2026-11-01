import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Navigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { AREA_PATH, useMe, type Me } from "../auth/useMe";
import {
  AGREE_ERROR,
  TermsCheckbox,
  requiredTerms,
  shownVersions,
  sitterTermsReady,
} from "../auth/TermsAgreement";
import { Button, Photo, RoleChooser, TextInput, type ChosenRole } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";

type Step = "role" | "details" | "confirm";
type SignUp = {
  role: ChosenRole;
  full_name: string;
  phone: string;
  pin_code: string;
  accepted: ReturnType<typeof shownVersions>;
};
type FieldErrors = { full_name?: string; phone?: string; pin_code?: string };

const NAME_ERROR = "Please tell us your full name.";
const PHONE_ERROR = "That number doesn't look quite right — could you check it? We need a 10-digit mobile number.";

// Same rule as the API (app/services/accounts.py): Indian mobile, optionally with +91, 91 or 0.
export function isIndianMobile(raw: string): boolean {
  return /^(?:\+?91|0)?[6-9]\d{9}$/.test(raw.replace(/[\s\-().]/g, ""));
}

export function outsideAreaMessage(pinCode: string, pinCodes: string[] | undefined): string {
  const list = pinCodes?.length ? ` For now we're in these Bengaluru pin codes: ${pinCodes.join(", ")}.` : "";
  return `Pacify isn't in ${pinCode} yet.${list}`;
}

const FIELD_MESSAGES: Record<keyof FieldErrors, string> = {
  full_name: NAME_ERROR,
  phone: PHONE_ERROR,
  pin_code: "Please enter your home pin code.",
};

// The API's validation details look like [{"field": "body.phone", "message": ...}]. Use our own wording.
export function fieldErrorsFrom(details: unknown): FieldErrors {
  const errors: FieldErrors = {};
  if (!Array.isArray(details)) return errors;
  for (const detail of details) {
    const field = String((detail as { field?: unknown })?.field ?? "").split(".").pop() as keyof FieldErrors;
    if (field in FIELD_MESSAGES) errors[field] = FIELD_MESSAGES[field];
  }
  return errors;
}

// `pinCodes` is the service area from the API; if it couldn't load, the API still checks on sign-up.
function checkDetails(details: Omit<SignUp, "role" | "accepted">, pinCodes: string[] | undefined): FieldErrors {
  const errors: FieldErrors = {};
  if (!details.full_name.trim()) errors.full_name = NAME_ERROR;
  if (!isIndianMobile(details.phone)) errors.phone = PHONE_ERROR;
  if (!/^[0-9]{6}$/.test(details.pin_code)) {
    errors.pin_code = "Pin codes have 6 digits — could you check it?";
  } else if (pinCodes && !pinCodes.includes(details.pin_code)) {
    errors.pin_code = outsideAreaMessage(details.pin_code, pinCodes);
  }
  return errors;
}

// After the first sign-in: parent or sitter, name and mobile, then a confirmation, because people can't
// change their role themselves later (CLAUDE.md 6.13).
export function JoinPage() {
  const { status, userId, name } = useAuth();
  const me = useMe();
  const queryClient = useQueryClient();
  const [step, setStep] = useState<Step>("role");
  const [role, setRole] = useState<ChosenRole | null>(null);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [pinCode, setPinCode] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  // Shown on the details step when the API refuses the form for a reason we can't pin to one field.
  const [formError, setFormError] = useState<string>();
  const [agreed, setAgreed] = useState(false);
  const [agreeError, setAgreeError] = useState<string>();
  const serviceArea = useQuery({
    queryKey: ["service-area"],
    queryFn: () => apiFetch<{ pin_codes: string[] }>("/service-area"),
    staleTime: 60 * 60 * 1000,
  });

  const signUp = useMutation({
    mutationFn: (body: SignUp) => apiFetch<Me>("/me/profile", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (created) => queryClient.setQueryData(["me", userId], created),
    onError: (error) => {
      // Already set up (e.g. in another tab): reload who they are, and this page moves them on.
      if (error instanceof ApiError && error.code === "already_signed_up") {
        void queryClient.invalidateQueries({ queryKey: ["me", userId] });
      }
      if (error instanceof ApiError && error.code === "validation_error") {
        const errors = fieldErrorsFrom(error.details);
        setFieldErrors(errors);
        setFormError(
          Object.keys(errors).length ? undefined : "Something didn't go through. Please reload the page and try again.",
        );
        setStep("details");
      }
      if (error instanceof ApiError && error.code === "outside_service_area") {
        setFieldErrors({ pin_code: outsideAreaMessage(pinCode, serviceArea.data?.pin_codes) });
        setStep("details");
      }
    },
  });

  if (status === "signed_out") return <Navigate to="/sign-in" replace />;
  if (status === "loading" || me.isPending) return <p className="text-center text-muted">Loading your account…</p>;
  if (me.isError) return <p className="text-center text-muted">{me.error.message}</p>;
  if (me.data.profile) return <Navigate to={AREA_PATH[me.data.profile.role]} replace />;

  function submitDetails(event: FormEvent) {
    event.preventDefault();
    const errors = checkDetails({ full_name: fullName, phone, pin_code: pinCode }, serviceArea.data?.pin_codes);
    setFieldErrors(errors);
    setFormError(undefined);
    if (Object.keys(errors).length === 0) {
      signUp.reset(); // don't show an earlier attempt's error on the confirmation
      setStep("confirm");
    }
  }

  if (step === "role" || !role) {
    return (
      <section className="mx-auto max-w-[44rem] text-center">
        <h1>How will you use Pacify?</h1>
        <p className="mt-4 text-muted">Choose one. Each account is either a parent or a sitter.</p>
        <div className="mt-6">
          <RoleChooser value={role} onChange={setRole} />
        </div>
        <div className="mt-6 flex justify-center">
          <Button
            arrow
            disabled={!role}
            onClick={() => {
              if (!fullName.trim() && name) setFullName(name);
              setStep("details");
            }}
          >
            Continue
          </Button>
        </div>
      </section>
    );
  }

  const roleLabel = role === "parent" ? "a parent" : "a sitter";

  if (step === "details") {
    return (
      <section className="mx-auto max-w-[28rem] text-center">
        <Photo
          name={role === "parent" ? "parentsDinnerCouple" : "sitterBubbles"}
          aspect="16 / 10"
          sizes="(min-width: 640px) 28rem, 100vw"
          priority
          className="mb-6"
        />
        <h1>A little about you.</h1>
        <p className="mt-4 text-muted">
          Joining as {roleLabel}.{" "}
          <Button variant="tertiary" onClick={() => setStep("role")}>
            Change
          </Button>
        </p>
        {formError && (
          <p role="alert" className="mt-4 text-small text-danger">
            {formError}
          </p>
        )}
        <form onSubmit={submitDetails} className="mt-6 flex flex-col gap-5 text-left" noValidate>
          <TextInput
            label="Full name"
            name="full_name"
            autoComplete="name"
            maxLength={100}
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            error={fieldErrors.full_name}
          />
          <TextInput
            label="Mobile number"
            name="phone"
            type="tel"
            autoComplete="tel"
            inputMode="tel"
            maxLength={20}
            hint="Pacify uses it to reach you about introductions and bookings."
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            error={fieldErrors.phone}
          />
          <TextInput
            label="Home pin code"
            name="pin_code"
            autoComplete="postal-code"
            inputMode="numeric"
            maxLength={6}
            hint="Pacify is starting in a few Bengaluru neighbourhoods."
            value={pinCode}
            onChange={(event) => setPinCode(event.target.value.replace(/\D/g, ""))}
            error={fieldErrors.pin_code}
          />
          <Button type="submit" arrow fullWidthOnPhone={false} className="w-full">
            Continue
          </Button>
        </form>
      </section>
    );
  }

  const failure = signUp.error instanceof ApiError ? signUp.error : null;
  const kinds = requiredTerms(role);
  // Production can't take sitters until every Sitter Terms placeholder is filled (CLAUDE.md 7).
  const sitterClosed = role === "sitter" && !sitterTermsReady();

  function createAccount() {
    if (!role) return;
    if (!agreed) return setAgreeError(AGREE_ERROR);
    setAgreeError(undefined);
    signUp.mutate({
      role,
      full_name: fullName.trim(),
      phone: phone.trim(),
      pin_code: pinCode,
      accepted: shownVersions(kinds),
    });
  }

  if (sitterClosed) {
    return (
      <section className="mx-auto max-w-[36rem] text-center">
        <h1>Sitter sign-up opens soon.</h1>
        <p className="mt-4 text-muted">
          We're finishing the Sitter Terms of Use. Please check back soon, or contact us at query.pacifyco@gmail.com.
        </p>
        <div className="mt-6 flex justify-center">
          <Button variant="secondary" onClick={() => setStep("role")}>
            Go back
          </Button>
        </div>
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-[36rem] text-center">
      <h1>You're joining as {roleLabel}.</h1>
      <p className="mt-4 text-muted">Is that right? Once your account is set up, only the Pacify team can change this.</p>
      <div className="mt-6 rounded-lg bg-surface-sunken p-5">
        <TermsCheckbox
          kinds={kinds}
          checked={agreed}
          onChange={(checked) => {
            setAgreed(checked);
            if (checked) setAgreeError(undefined);
          }}
          error={agreeError}
        />
      </div>
      {failure && !["already_signed_up", "outside_service_area"].includes(failure.code) && (
        <p role="alert" className="mt-4 text-small text-danger">
          {failure.code === "email_in_use"
            ? "This email already has a Pacify account. Please sign in with a different email, or contact us."
            : failure.code === "terms_outdated"
              ? "Our terms have been updated. Please reload the page to read the new version."
              : failure.message}
        </p>
      )}
      <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:justify-center">
        <Button
          arrow
          loading={signUp.isPending}
          onClick={createAccount}
        >
          Yes, create my account
        </Button>
        <Button variant="secondary" disabled={signUp.isPending} onClick={() => setStep("role")}>
          Go back
        </Button>
      </div>
    </section>
  );
}
