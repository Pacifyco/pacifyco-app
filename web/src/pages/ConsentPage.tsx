import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "../auth/AuthProvider";
import { Button, Checkbox } from "../components/ui";
import consentSource from "../content/consent.md?raw";
import { apiFetch } from "../lib/api";
import { formatDate } from "../lib/format";
import { Markdown, parseDocument } from "../lib/markdown";

export const CONSENT = parseDocument(consentSource);
export const CONSENT_VERSION = CONSENT.meta.version ?? "";

export type ConsentStatus = { version: string; accepted_at: string | null };

export function useConsent() {
  const { userId } = useAuth();
  return useQuery({
    queryKey: ["consent", userId],
    queryFn: () => apiFetch<ConsentStatus>("/parent/consent"),
  });
}

// CLAUDE.md 7: before any child documents, the parent accepts the current version of this form.
export function ConsentPage() {
  const { userId } = useAuth();
  const queryClient = useQueryClient();
  const consent = useConsent();
  const [ticked, setTicked] = useState(false);
  const [error, setError] = useState<string>();

  const accept = useMutation({
    mutationFn: () =>
      apiFetch<ConsentStatus>("/parent/consent", {
        method: "POST",
        body: JSON.stringify({ version: CONSENT_VERSION }),
      }),
    onSuccess: (status) => queryClient.setQueryData(["consent", userId], status),
  });

  // The API and this page disagree about the current version: an old copy of the app is open.
  const outdated = consent.isSuccess && consent.data.version !== CONSENT_VERSION;
  const acceptedAt = consent.data && !outdated ? consent.data.accepted_at : null;

  function submit() {
    if (!ticked) return setError("Please tick the box to give your consent.");
    setError(undefined);
    accept.mutate();
  }

  return (
    <article className="mx-auto max-w-[62ch]">
      <Markdown body={CONSENT.body} />
      <p className="mt-4 text-small text-muted">Version {CONSENT_VERSION}</p>

      <div className="mt-6 rounded-lg bg-surface-sunken p-5">
        {consent.isPending ? (
          <p className="text-muted">Checking your consent…</p>
        ) : consent.isError ? (
          <p className="text-muted">{consent.error.message}</p>
        ) : outdated ? (
          <p role="alert" className="text-small text-danger">
            This form has been updated. Please reload the page to read the new version.
          </p>
        ) : acceptedAt ? (
          <p className="text-ink">You gave your consent on {formatDate(new Date(acceptedAt))}.</p>
        ) : (
          <div className="flex flex-col gap-5">
            <Checkbox
              label="I'm the parent or legal guardian of the children I add, and I give my consent as described above."
              checked={ticked}
              onChange={(event) => setTicked(event.target.checked)}
              error={error}
            />
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
