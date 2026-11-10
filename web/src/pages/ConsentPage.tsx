import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { BackLink, Button, ButtonLink, Checkbox } from "../components/ui";
import consentSource from "../content/consent.md?raw";
import { apiFetch } from "../lib/api";
import { formatDate } from "../lib/format";
import { Markdown, parseDocument } from "../lib/markdown";

export const CONSENT = parseDocument(consentSource);
export const CONSENT_VERSION = CONSENT.meta.version ?? "";

export type ConsentStatus = {
  version: string;
  required_accepted: boolean;
  accepted_at: string | null;
  marketing: boolean;
};

export function useConsent() {
  const { userId } = useAuth();
  return useQuery({
    queryKey: ["consent", userId],
    queryFn: () => apiFetch<ConsentStatus>("/parent/consent"),
  });
}

// Family Terms 11.2 (CLAUDE.md 7): four required consents, ticked separately, nothing pre-ticked.
const REQUIRED_LABELS = [
  "I consent to Pacify's use of my own data for my account, verification, bookings, payments and safety.",
  "I consent to Pacify's use of each child's data, given by me as their parent or guardian, to match and brief a sitter and keep my child safe.",
  "I consent to Pacify sharing my child's care details with the booked sitter.",
  "I give emergency authorisation: if I and my emergency contacts can't be reached, the sitter may call 112, take my child to the nearest hospital or doctor, and Pacify may share my child's health details with treating doctors.",
];
const MARKETING_LABEL =
  "I'd like offers and updates from Pacify. Saying no won't affect my service, and I can change my mind at any time.";

// CLAUDE.md 7: before any child documents, the parent accepts every required consent.
export function ConsentPage() {
  const { userId } = useAuth();
  const queryClient = useQueryClient();
  const consent = useConsent();
  const navigate = useNavigate();
  const [ticked, setTicked] = useState<boolean[]>(() => REQUIRED_LABELS.map(() => false));
  const [marketing, setMarketing] = useState(false);
  const [error, setError] = useState<string>();

  const accept = useMutation({
    mutationFn: () =>
      apiFetch<ConsentStatus>("/parent/consent", {
        method: "POST",
        body: JSON.stringify({ version: CONSENT_VERSION, marketing }),
      }),
    onSuccess: async (status) => {
      queryClient.setQueryData(["consent", userId], status);
      await queryClient.invalidateQueries({ queryKey: ["checklist"] });
      navigate("/parent/profile"); // back to the checklist, which now shows consent as done
    },
  });

  const setMarketingChoice = useMutation({
    mutationFn: (accepted: boolean) =>
      apiFetch<ConsentStatus>("/parent/consent/marketing", { method: "PATCH", body: JSON.stringify({ accepted }) }),
    onSuccess: (status) => queryClient.setQueryData(["consent", userId], status),
  });

  // The API and this page disagree about the current version: an old copy of the app is open.
  const outdated = consent.isSuccess && consent.data.version !== CONSENT_VERSION;
  const acceptedAt = consent.data && !outdated ? consent.data.accepted_at : null;
  const marketingGiven = consent.data && !outdated ? consent.data.marketing : false;

  function submit() {
    if (ticked.some((value) => !value)) return setError("Please tick every required box to continue.");
    setError(undefined);
    accept.mutate();
  }

  return (
    <article className="mx-auto max-w-[62ch]">
      <div className="mb-4">
        <BackLink to="/parent/profile" label="Your profile" />
      </div>
      <Markdown body={CONSENT.body} />
      <p className="mt-4 text-small text-muted">Version {CONSENT_VERSION}</p>

      <div className="mt-6 flex flex-col gap-5 rounded-lg bg-surface-sunken p-5">
        {consent.isPending ? (
          <p className="text-muted">Checking your consent…</p>
        ) : consent.isError ? (
          <p className="text-muted">{consent.error.message}</p>
        ) : outdated ? (
          <p role="alert" className="text-small text-danger">
            This form has been updated. Please reload the page to read the new version.
          </p>
        ) : acceptedAt ? (
          <div className="flex flex-col items-start gap-4">
            <p className="text-ink">You gave your consent on {formatDate(new Date(acceptedAt))}.</p>
            <Checkbox
              label={MARKETING_LABEL}
              checked={marketingGiven}
              onChange={(event) => setMarketingChoice.mutate(event.target.checked)}
            />
            <ButtonLink to="/parent/profile" variant="secondary">
              Back to your profile
            </ButtonLink>
          </div>
        ) : (
          <>
            {REQUIRED_LABELS.map((label, index) => (
              <Checkbox
                key={label}
                label={label}
                checked={ticked[index]}
                onChange={(event) =>
                  setTicked((current) => current.map((value, i) => (i === index ? event.target.checked : value)))
                }
              />
            ))}
            <Checkbox label={MARKETING_LABEL} checked={marketing} onChange={(event) => setMarketing(event.target.checked)} />
            {error && (
              <p role="alert" className="text-small text-danger">
                {error}
              </p>
            )}
            {accept.isError && (
              <p role="alert" className="text-small text-danger">
                {accept.error.message}
              </p>
            )}
            <Button loading={accept.isPending} onClick={submit}>
              I agree
            </Button>
          </>
        )}
      </div>
    </article>
  );
}
