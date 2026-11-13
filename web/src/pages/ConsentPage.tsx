import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { TermsCheckbox, requiredTerms, shownVersions, termsOutdated, termsReady } from "../auth/TermsAgreement";
import { useMe, type Me } from "../auth/useMe";
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
  "I consent to Pacifyco's use of my own data for my account, verification, bookings, payments and safety.",
  "I consent to Pacifyco's use of each child's data, given by me as their parent or guardian, to match and brief a sitter and keep my child safe.",
  "I consent to Pacifyco sharing my child's care details with the booked sitter.",
  "I give emergency authorisation: if I and my emergency contacts can't be reached, the sitter may call 112, take my child to the nearest hospital or doctor, and Pacifyco may share my child's health details with treating doctors.",
];
const MARKETING_LABEL =
  "I'd like offers and updates from Pacifyco. Saying no won't affect my service, and I can change my mind at any time.";

const TERMS = requiredTerms("parent");
const TICK_EVERY_BOX = "Please tick every required box to continue.";

// CLAUDE.md 7: before any child documents, the parent accepts every required consent, and on the same
// page the Family Terms of Use and privacy policy (moved here from sign-up, decided 2026-11-12).
export function ConsentPage() {
  const { userId } = useAuth();
  const queryClient = useQueryClient();
  const consent = useConsent();
  const me = useMe();
  const navigate = useNavigate();
  const [ticked, setTicked] = useState<boolean[]>(() => REQUIRED_LABELS.map(() => false));
  const [termsTicked, setTermsTicked] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [error, setError] = useState<string>();
  // After a try with boxes missing, each unticked required box is outlined (UX review 2026-11-13).
  const [tried, setTried] = useState(false);
  const boxes = useRef<HTMLDivElement>(null);

  async function done() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["checklist"] }),
      queryClient.invalidateQueries({ queryKey: ["me", userId] }),
    ]);
    navigate("/parent/profile"); // back to the checklist, which now shows consent as done
  }

  const accept = useMutation({
    mutationFn: () =>
      apiFetch<ConsentStatus>("/parent/consent", {
        method: "POST",
        body: JSON.stringify({ version: CONSENT_VERSION, marketing, accepted: shownVersions(TERMS) }),
      }),
    onSuccess: async (status) => {
      queryClient.setQueryData(["consent", userId], status);
      await done();
    },
  });

  // Consent given before, but there's a new version of the terms or privacy policy to accept.
  const toAccept = me.data?.terms_to_accept ?? [];
  const acceptTerms = useMutation({
    mutationFn: () =>
      apiFetch<Me>("/me/terms", {
        method: "POST",
        body: JSON.stringify({ accepted: shownVersions(toAccept.map((item) => item.kind)) }),
      }),
    onSuccess: async (updated) => {
      queryClient.setQueryData(["me", userId], updated);
      await done();
    },
  });

  const setMarketingChoice = useMutation({
    mutationFn: (accepted: boolean) =>
      apiFetch<ConsentStatus>("/parent/consent/marketing", { method: "PATCH", body: JSON.stringify({ accepted }) }),
    onSuccess: (status) => queryClient.setQueryData(["consent", userId], status),
  });

  // The API and this page disagree about the current version: an old copy of the app is open.
  const outdated = (consent.isSuccess && consent.data.version !== CONSENT_VERSION) || termsOutdated(toAccept);
  const acceptedAt = consent.data && !outdated ? consent.data.accepted_at : null;
  const marketingGiven = consent.data && !outdated ? consent.data.marketing : false;

  function submit() {
    if (ticked.some((value) => !value) || !termsTicked) {
      setTried(true);
      setError(TICK_EVERY_BOX);
      // Move to the first box still to tick.
      const boxesLeft = boxes.current?.querySelectorAll<HTMLInputElement>("input[type=checkbox][data-required]");
      [...(boxesLeft ?? [])].find((box) => !box.checked)?.focus();
      return;
    }
    setError(undefined);
    accept.mutate();
  }

  function submitTerms() {
    if (!termsTicked) return setError(TICK_EVERY_BOX);
    setError(undefined);
    acceptTerms.mutate();
  }

  return (
    <article className="mx-auto max-w-[62ch]">
      <div className="mb-4">
        <BackLink to="/parent/profile" label="Your profile" />
      </div>
      <Markdown body={CONSENT.body} />
      <p className="mt-4 text-small text-muted">Version {CONSENT_VERSION}</p>

      <div className="mt-6 flex flex-col gap-5 rounded-lg bg-surface-sunken p-5">
        {consent.isPending || me.isPending ? (
          <p className="text-muted">Checking your consent…</p>
        ) : consent.isError ? (
          <p className="text-muted">{consent.error.message}</p>
        ) : outdated ? (
          <p role="alert" className="text-small text-danger">
            This form has been updated. Please reload the page to read the new version.
          </p>
        ) : !termsReady("parent") ? (
          <p className="text-muted">Our terms aren't available yet. Please check back soon.</p>
        ) : acceptedAt && toAccept.length ? (
          <>
            <p className="text-ink">
              You gave your consent on {formatDate(new Date(acceptedAt))}. We've updated our terms since then: please
              read them and tick to agree.
            </p>
            <TermsCheckbox
              kinds={toAccept.map((item) => item.kind)}
              checked={termsTicked}
              onChange={setTermsTicked}
              error={error}
            />
            {acceptTerms.isError && (
              <p role="alert" className="text-small text-danger">
                {acceptTerms.error.message}
              </p>
            )}
            <Button loading={acceptTerms.isPending} onClick={submitTerms}>
              I agree
            </Button>
          </>
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
          <div ref={boxes} className="flex flex-col gap-5">
            {REQUIRED_LABELS.map((label, index) => (
              <Checkbox
                key={label}
                tag="Required"
                data-required
                highlight={tried && !ticked[index]}
                label={label}
                checked={ticked[index]}
                onChange={(event) =>
                  setTicked((current) => current.map((value, i) => (i === index ? event.target.checked : value)))
                }
              />
            ))}
            <TermsCheckbox
              kinds={TERMS}
              tag="Required"
              highlight={tried && !termsTicked}
              checked={termsTicked}
              onChange={setTermsTicked}
            />
            <div className="flex items-center gap-3 text-eyebrow text-muted uppercase" aria-hidden="true">
              <span className="h-px flex-1 bg-line" />
              Optional
              <span className="h-px flex-1 bg-line" />
            </div>
            <Checkbox
              tag="Optional"
              label={MARKETING_LABEL}
              checked={marketing}
              onChange={(event) => setMarketing(event.target.checked)}
            />
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
          </div>
        )}
      </div>
    </article>
  );
}
