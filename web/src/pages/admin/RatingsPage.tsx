import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { Stars } from "../../components/ReviewCard";
import { BackLink, Button, Card, EmptyState, Textarea, showToast } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDate, formatDay, formatMobile, formatTime } from "../../lib/format";
import { errorMessage } from "./shared";

// Low ratings (CLAUDE.md 6.11): sitters whose average over their last 10 reviews fell below 3.5 (once they
// have 5; Reuben, 2026-11-22). Before any removal for ratings she must be told the reason and given a chance
// to respond, which is recorded: tell her, read her response, then close the flag with a note. She has 12
// hours from being told (Reuben, 2026-11-22); closing waits for her response or the end of those 12 hours.
// Removing an account is a separate step (phase 10).

export type RatingFlag = {
  id: string;
  sitter_id: string;
  sitter_name: string | null;
  sitter_phone: string | null;
  average: number;
  reviews_counted: number;
  status: "open" | "told" | "responded";
  created_at: string;
  reason: string | null;
  told_at: string | null;
  response: string | null;
  responded_at: string | null;
  respond_by: string | null; // her 12 hours to respond end (Reuben, 2026-11-22)
  can_close: boolean; // not told yet, or she has responded or her 12 hours have passed
};

const FLAGS_KEY = ["admin", "rating-flags"];

function NoteForm({
  flag,
  action,
  label,
  hint,
  button,
  done,
}: {
  flag: RatingFlag;
  action: "tell" | "close";
  label: string;
  hint: string;
  button: string;
  done: string;
}) {
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | undefined>();
  const send = useMutation({
    mutationFn: () =>
      apiFetch<RatingFlag>(`/admin/rating-flags/${flag.id}/${action}`, {
        method: "POST",
        body: JSON.stringify(action === "tell" ? { reason: text.trim() } : { note: text.trim() }),
      }),
    onSuccess: async () => {
      showToast(done);
      setText("");
      await queryClient.invalidateQueries({ queryKey: FLAGS_KEY });
    },
    onError: (failed) => setError(errorMessage(failed)),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return setError(action === "tell" ? "Tell her the reason." : "Add a note on what you decided.");
    setError(undefined);
    send.mutate();
  }

  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-3">
      <Textarea
        label={label}
        hint={hint}
        rows={3}
        maxLength={1000}
        value={text}
        error={error}
        onChange={(event) => setText(event.target.value)}
      />
      <div>
        <Button type="submit" variant="secondary" loading={send.isPending} fullWidthOnPhone={false}>
          {button}
        </Button>
      </div>
    </form>
  );
}

function FlagItem({ flag }: { flag: RatingFlag }) {
  return (
    <li className="flex flex-col gap-3 border-t border-line py-5 first:border-t-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <Link to={`/admin/sitters/${flag.sitter_id}`} className="text-ui">
          {flag.sitter_name ?? "Name not given"}
        </Link>
        <p className="text-ui text-danger">
          {flag.average.toFixed(1)} over her last {flag.reviews_counted} reviews
        </p>
      </div>
      <p className="text-small text-muted">Flagged {formatDate(new Date(flag.created_at))}</p>
      {flag.sitter_phone && (
        <a href={`tel:${flag.sitter_phone}`} className="text-ui">
          {formatMobile(flag.sitter_phone)}
        </a>
      )}
      {flag.status === "open" ? (
        <NoteForm
          flag={flag}
          action="tell"
          label="Tell her the reason"
          hint="She sees this in the app and by email, and can respond."
          button="Tell her"
          done="She's been told and can respond."
        />
      ) : (
        <>
          <p className="text-small text-muted">
            Told {flag.told_at ? formatDate(new Date(flag.told_at)) : ""}:
          </p>
          <p className="whitespace-pre-line text-ink">{flag.reason}</p>
          {flag.response ? (
            <>
              <p className="text-small text-muted">
                Her response{flag.responded_at ? `, ${formatDate(new Date(flag.responded_at))}` : ""}:
              </p>
              <p className="whitespace-pre-line text-ink">{flag.response}</p>
            </>
          ) : flag.can_close ? (
            <p className="text-muted">She didn't respond within 12 hours.</p>
          ) : (
            <p className="text-muted">
              Waiting for her response. She has until{" "}
              {flag.respond_by ? `${formatDay(new Date(flag.respond_by))}, ${formatTime(new Date(flag.respond_by))}` : "12 hours after being told"}
              .
            </p>
          )}
        </>
      )}
      {flag.can_close && (
        <NoteForm
          flag={flag}
          action="close"
          label="Close with a note"
          hint={
            flag.status === "open"
              ? "Only if no action is needed: she hasn't been told. Only admins see the note."
              : "What you decided and why. Only admins see it."
          }
          button="Close the flag"
          done="Flag closed."
        />
      )}
    </li>
  );
}

export function RatingsPage() {
  const flags = useQuery({ queryKey: FLAGS_KEY, queryFn: () => apiFetch<RatingFlag[]>("/admin/rating-flags") });
  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-4">
      <BackLink to="/admin" label="Admin" />
      <h1>Low ratings</h1>
      <p className="text-muted">
        Sitters whose average over their last 10 reviews is below 3.5. Tell her the reason and give her a chance to
        respond before deciding anything.
      </p>
      {flags.isPending && <p className="text-muted">Loading…</p>}
      {flags.isError && (
        <p role="alert" className="text-danger">
          {errorMessage(flags.error)}
        </p>
      )}
      {flags.isSuccess &&
        (flags.data.length === 0 ? (
          <EmptyState message="No sitters flagged for low ratings." />
        ) : (
          <Card as="section" padding="roomy" aria-label="Flagged sitters">
            <ul>
              {flags.data.map((flag) => (
                <FlagItem key={flag.id} flag={flag} />
              ))}
            </ul>
          </Card>
        ))}
    </section>
  );
}

/** A review as admins see it: the author's full name and the booking (6.11). */
export type ReviewForAdmin = {
  id: string;
  booking_id: string;
  rating: number;
  body: string | null;
  author_name: string | null;
  created_at: string;
};

/** Reviews about one person, for their admin page. */
export function AdminReviews({ title, reviews, summary }: { title: string; reviews: ReviewForAdmin[]; summary?: string }) {
  return (
    <Card as="section" padding="roomy" aria-label={title} className="flex flex-col gap-3">
      <h2 className="text-h3">{title}</h2>
      {summary && <p className="text-muted">{summary}</p>}
      {reviews.length === 0 ? (
        <p className="text-muted">No reviews yet.</p>
      ) : (
        <ul className="flex flex-col">
          {reviews.map((review) => (
            <li key={review.id} className="flex flex-col gap-1 border-t border-line py-3 first:border-t-0">
              <Stars rating={review.rating} />
              {review.body && <p className="whitespace-pre-line text-ink">{review.body}</p>}
              <p className="text-small text-muted">
                {review.author_name ?? "Name not given"} · {formatDate(new Date(review.created_at))}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
