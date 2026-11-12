import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import {
  SITTER_CONSENT,
  TermsCheckbox,
  requiredTerms,
  shownVersions,
  termsOutdated,
  termsReady,
} from "../auth/TermsAgreement";
import { useMe, type Me, type TermsKind } from "../auth/useMe";
import { BackLink, Button, ButtonLink, Checkbox } from "../components/ui";
import { apiFetch } from "../lib/api";
import { Markdown } from "../lib/markdown";

// Everything a sitter accepts, on one page (decided 2026-11-12): the sitter consent
// (web/src/content/sitter-consent-v*.md, Reuben's wording), the Sitter Terms of Use and the privacy
// policy. Each is a versioned document recorded by click-wrap (POST /me/terms). Admins can't approve
// her until it's done.
const KINDS: TermsKind[] = ["sitter_consent", ...requiredTerms("sitter")];
const CONSENT_LABEL = "I've read these and I'll follow them.";
const TICK_BOTH = "Please tick both boxes to continue.";

export function SitterConsentPage() {
  const { userId } = useAuth();
  const queryClient = useQueryClient();
  const me = useMe();
  const navigate = useNavigate();
  const [consentTicked, setConsentTicked] = useState(false);
  const [termsTicked, setTermsTicked] = useState(false);
  const [error, setError] = useState<string>();

  const accept = useMutation({
    mutationFn: () =>
      apiFetch<Me>("/me/terms", {
        method: "POST",
        body: JSON.stringify({ accepted: shownVersions(KINDS) }),
      }),
    onSuccess: async (updated) => {
      queryClient.setQueryData(["me", userId], updated);
      await queryClient.invalidateQueries({ queryKey: ["checklist"] });
      navigate("/sitter/profile"); // back to the checklist, which now shows this as done
    },
  });

  const toAccept = (me.data?.terms_to_accept ?? []).filter((item) => KINDS.includes(item.kind));

  function submit() {
    if (!consentTicked || !termsTicked) return setError(TICK_BOTH);
    setError(undefined);
    accept.mutate();
  }

  return (
    <article className="mx-auto max-w-[62ch]">
      <div className="mb-4">
        <BackLink to="/sitter/profile" label="Your profile" />
      </div>
      <h1>Sitter consent</h1>
      <Markdown body={SITTER_CONSENT.body} />
      <p className="mt-4 text-small text-muted">Version {SITTER_CONSENT.meta.version}</p>

      <div className="mt-6 flex flex-col gap-5 rounded-lg bg-surface-sunken p-5">
        {me.isPending ? (
          <p className="text-muted">Checking what you've accepted…</p>
        ) : me.isError ? (
          <p className="text-muted">{me.error.message}</p>
        ) : termsOutdated(toAccept) ? (
          <p role="alert" className="text-small text-danger">
            This page has been updated. Please reload it to read the new version.
          </p>
        ) : toAccept.length === 0 ? (
          <div className="flex flex-col items-start gap-4">
            <p className="text-ink">You've accepted these. When we change them, we'll ask you again.</p>
            <ButtonLink to="/sitter/profile" variant="secondary">
              Back to your profile
            </ButtonLink>
          </div>
        ) : !termsReady("sitter") ? (
          <p className="text-muted">Our terms aren't available yet. Please check back soon.</p>
        ) : (
          <>
            <Checkbox
              className="text-left"
              label={CONSENT_LABEL}
              checked={consentTicked}
              onChange={(event) => setConsentTicked(event.target.checked)}
            />
            <TermsCheckbox kinds={requiredTerms("sitter")} checked={termsTicked} onChange={setTermsTicked} />
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
