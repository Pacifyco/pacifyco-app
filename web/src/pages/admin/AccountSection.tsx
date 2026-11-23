import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Button, Card, Select, Textarea } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDay, formatTime, plural } from "../../lib/format";
import { errorMessage } from "./shared";

// Suspend, remove or reinstate a parent or sitter (phase 10; Reuben, 2026-11-22). The person is emailed
// the reason. Their upcoming bookings are cancelled and refunded, with no strike. A low-ratings decision
// waits until she has responded to her flag, or her 12 hours have passed (6.11).

export type AccountKind = "low_ratings" | "safety" | "strikes" | "other";

export type AccountAction = {
  action: "suspended" | "removed" | "reinstated";
  kind: AccountKind | null;
  reason: string;
  by: string | null;
  at: string;
};

export type AdminAccount = {
  id: string;
  role: "parent" | "sitter";
  status: "pending" | "active" | "suspended" | "removed";
  upcoming_bookings: number;
  under_way_bookings: number;
  ratings_wait: string | null;
  five_strikes: boolean;
  history: AccountAction[];
};

export const ACCOUNT_STATUS_WORDS: Record<AdminAccount["status"], string> = {
  pending: "Not verified yet",
  active: "Active",
  suspended: "Suspended",
  removed: "Removed",
};

const KIND_WORDS: Record<AccountKind, string> = {
  low_ratings: "Low ratings",
  safety: "Safety or conduct",
  strikes: "Strikes",
  other: "Other",
};

const ACTION_WORDS: Record<AccountAction["action"], string> = {
  suspended: "Suspended",
  removed: "Removed",
  reinstated: "Reinstated",
};

type Choice = "suspend" | "remove" | "reinstate";

export function accountKey(profileId: string) {
  return ["admin", "account", profileId];
}

function when(iso: string): string {
  const moment = new Date(iso);
  return `${formatDay(moment)}, ${formatTime(moment)}`;
}

function ActionForm({ account, choice, onDone }: { account: AdminAccount; choice: Choice; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<AccountKind | "">("");
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<{ kind?: string; reason?: string }>({});
  const send = useMutation({
    mutationFn: () =>
      apiFetch<AdminAccount>(`/admin/accounts/${account.id}/${choice}`, {
        method: "POST",
        body: JSON.stringify(choice === "reinstate" ? { reason: reason.trim() } : { kind, reason: reason.trim() }),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(accountKey(account.id), updated);
      onDone();
    },
  });
  const blocking = choice !== "reinstate";
  const kinds: AccountKind[] =
    account.role === "sitter" ? ["safety", "low_ratings", "strikes", "other"] : ["safety", "other"];

  function submit(event: FormEvent) {
    event.preventDefault();
    const found: typeof errors = {};
    if (blocking && !kind) found.kind = "Choose the kind of reason.";
    if (!reason.trim()) found.reason = "Please give a reason. The person will see it.";
    setErrors(found);
    if (Object.keys(found).length === 0) send.mutate();
  }

  const submitLabel =
    choice === "suspend" ? "Suspend the account" : choice === "remove" ? "Remove the account" : "Reinstate";
  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-3 border-t border-line pt-4">
      {blocking && (
        <Select
          label="Kind of reason"
          value={kind}
          onChange={(event) => setKind(event.target.value as AccountKind)}
          error={errors.kind}
        >
          <option value="">Choose…</option>
          {kinds.map((item) => (
            <option key={item} value={item}>
              {KIND_WORDS[item]}
            </option>
          ))}
        </Select>
      )}
      {kind === "low_ratings" && account.ratings_wait && (
        <p className="text-small text-danger">{account.ratings_wait}</p>
      )}
      <Textarea
        label={blocking ? "The reason. They'll see this in an email." : "Why reinstate? They'll see this in an email."}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        error={errors.reason}
      />
      {blocking && account.upcoming_bookings > 0 && (
        <p className="text-small text-ink">
          This cancels {plural(account.upcoming_bookings, "upcoming booking", "upcoming bookings")} and refunds any
          money paid. The {account.role === "sitter" ? "families are" : "sitters are"} told, with no reason given.
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="secondary" fullWidthOnPhone={false} loading={send.isPending}>
          {submitLabel}
        </Button>
        <Button type="button" variant="tertiary" fullWidthOnPhone={false} onClick={onDone}>
          Cancel
        </Button>
      </div>
      {send.isError && (
        <p role="alert" className="text-small text-danger">
          {errorMessage(send.error)}
        </p>
      )}
    </form>
  );
}

export function AccountSection({ profileId }: { profileId: string }) {
  const account = useQuery({
    queryKey: accountKey(profileId),
    queryFn: () => apiFetch<AdminAccount>(`/admin/accounts/${profileId}`),
  });
  const [choice, setChoice] = useState<Choice | null>(null);

  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3" aria-labelledby="account-heading">
      <h2 id="account-heading" className="text-h3">
        Account
      </h2>
      {account.isPending && <p className="text-muted">Loading…</p>}
      {account.isError && (
        <p role="alert" className="text-danger">
          {errorMessage(account.error)}
        </p>
      )}
      {account.isSuccess && (
        <>
          <p
            className={
              account.data.status === "suspended" || account.data.status === "removed" ? "text-danger" : "text-ink"
            }
          >
            {ACCOUNT_STATUS_WORDS[account.data.status]}.
          </p>
          {account.data.under_way_bookings > 0 && (
            <p className="text-small text-ink">
              {plural(account.data.under_way_bookings, "booking is", "bookings are")} under way. Suspending or removing
              doesn't cancel {account.data.under_way_bookings === 1 ? "it" : "them"}: call both people.
            </p>
          )}
          {account.data.history.length > 0 && (
            <ul>
              {account.data.history.map((item) => (
                <li
                  key={`${item.at}-${item.action}`}
                  className="flex flex-col gap-1 border-t border-line py-3 first:border-t-0"
                >
                  <p className="text-ui text-ink">
                    {ACTION_WORDS[item.action]}
                    {item.kind ? ` · ${KIND_WORDS[item.kind]}` : ""} · {when(item.at)}
                  </p>
                  <p className="text-small text-ink">{item.reason}</p>
                  <p className="text-small text-muted">{item.by ? `By ${item.by}` : "By the rules"}</p>
                </li>
              ))}
            </ul>
          )}
          {choice ? (
            <ActionForm key={choice} account={account.data} choice={choice} onDone={() => setChoice(null)} />
          ) : (
            <div className="flex flex-wrap gap-3">
              {(account.data.status === "pending" || account.data.status === "active") && (
                <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setChoice("suspend")}>
                  Suspend
                </Button>
              )}
              {account.data.status !== "removed" && (
                <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setChoice("remove")}>
                  Remove
                </Button>
              )}
              {(account.data.status === "suspended" || account.data.status === "removed") &&
                (account.data.five_strikes ? (
                  <p className="text-small text-muted">
                    She has 5 strikes counting. Remove a strike before reinstating her.
                  </p>
                ) : (
                  <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setChoice("reinstate")}>
                    Reinstate
                  </Button>
                ))}
            </div>
          )}
        </>
      )}
    </Card>
  );
}
