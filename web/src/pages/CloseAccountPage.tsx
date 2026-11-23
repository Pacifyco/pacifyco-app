import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { BackLink, Button, Card, Checkbox, Textarea } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { rupees } from "../lib/prices";

// Closing their own account (CLAUDE.md 6.13; Reuben, 2026-11-23): once nothing is booked ahead or under
// way, and a parent owes nothing. A sitter's pay still due is paid as usual. Pacifyco can reopen it. No
// subheadings (CLAUDE.md 7).

export type Closing = { can_close: boolean; reasons: string[]; owed_paise: number; pay_due_paise: number };

export function CloseAccountPage({ role }: { role: "parent" | "sitter" }) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [sure, setSure] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closing = useQuery({ queryKey: ["closing"], queryFn: () => apiFetch<Closing>("/me/closing") });
  const close = useMutation({
    mutationFn: () =>
      apiFetch<{ status: string }>("/me/close", {
        method: "POST",
        body: JSON.stringify({ reason: reason.trim() || null }),
      }),
    // Who's signed in changes to closed, so the area shows the closed page.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["me"] }),
    onError: (failed) =>
      setError(failed instanceof ApiError ? failed.message : "That didn't go through. Please try again."),
  });

  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-6">
      <BackLink to={`/${role}/profile`} label="Your profile" />
      <h1>Close your account</h1>
      <p className="text-muted">
        Once it's closed, you can't use Pacifyco with this account
        {role === "sitter" ? " and families won't see you" : ""}. We keep the records the law requires us to. If you'd
        also like your data deleted, <Link to={`/${role}/help/new?data=deletion`}>ask us from Help</Link>. You can ask
        us to reopen it later.
      </p>
      {closing.isSuccess && (
        <Card padding="roomy" className="flex flex-col gap-4">
          {closing.data.can_close ? (
            <form
              noValidate
              onSubmit={(event) => {
                event.preventDefault();
                if (!sure) return setError("Please tick the box first.");
                setError(null);
                close.mutate();
              }}
              className="flex flex-col gap-4"
            >
              {closing.data.pay_due_paise > 0 && (
                <p className="text-ink">
                  The {rupees(closing.data.pay_due_paise)} you've earned and haven't been paid yet will still be paid
                  to you as usual.
                </p>
              )}
              <Textarea
                label="Why are you leaving?"
                optional
                maxLength={1000}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
              <Checkbox
                label="I understand I won't be able to use this account once it's closed."
                checked={sure}
                onChange={(event) => setSure(event.target.checked)}
              />
              {error && (
                <p role="alert" className="text-small text-danger">
                  {error}
                </p>
              )}
              <div>
                <Button type="submit" variant="secondary" loading={close.isPending} fullWidthOnPhone={false}>
                  Close my account
                </Button>
              </div>
            </form>
          ) : (
            <>
              <p className="text-ink">You can't close your account just yet:</p>
              <ul className="flex list-disc flex-col gap-2 pl-5 text-ink">
                {closing.data.reasons.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              {closing.data.owed_paise > 0 && (
                <p>
                  <Link to="/parent/payments">Pay the {rupees(closing.data.owed_paise)} you owe</Link>
                </p>
              )}
            </>
          )}
        </Card>
      )}
    </section>
  );
}
