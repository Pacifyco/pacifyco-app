import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { ReviewList, Stars, type PublicReview } from "../components/ReviewCard";
import { Button, Card, EmptyState, Textarea, showToast } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { formatDate, formatDay, formatTime, plural } from "../lib/format";

// Her reviews (CLAUDE.md 6.11): what families have said about her, as parents see it on her profile, and,
// if her ratings are being reviewed, the reason Pacifyco gave her and her response (recorded before any
// decision).

export type RatingFlagForHer = {
  id: string;
  reason: string;
  told_at: string;
  response: string | null;
  responded_at: string | null;
  respond_by: string; // 12 hours from being told (Reuben, 2026-11-22)
};

export type SitterReviews = {
  avg_rating: number | null;
  review_count: number;
  reviews: PublicReview[];
  flag: RatingFlagForHer | null;
};

export const REVIEWS_KEY = ["sitter", "reviews"];
const RESPONSE_MAX = 2000;

function Respond({ flag }: { flag: RatingFlagForHer }) {
  const queryClient = useQueryClient();
  const [response, setResponse] = useState("");
  const [error, setError] = useState<string | undefined>();
  const send = useMutation({
    mutationFn: () =>
      apiFetch<SitterReviews>(`/sitter/rating-flags/${flag.id}/respond`, {
        method: "POST",
        body: JSON.stringify({ response: response.trim() }),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(REVIEWS_KEY, updated);
      showToast("Thank you. We'll read it before we decide anything.");
    },
    onError: (failed) => setError(failed instanceof ApiError ? failed.message : "That didn't go through. Please try again."),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!response.trim()) return setError("Write your response.");
    setError(undefined);
    send.mutate();
  }

  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-3">
      <Textarea
        label="Your response"
        hint="Tell us your side. Pacifyco reads it before deciding anything."
        maxLength={RESPONSE_MAX}
        value={response}
        error={error}
        onChange={(event) => setResponse(event.target.value)}
      />
      <div>
        <Button type="submit" loading={send.isPending} fullWidthOnPhone={false}>
          Send your response
        </Button>
      </div>
    </form>
  );
}

function FlagCard({ flag }: { flag: RatingFlagForHer }) {
  return (
    <Card as="section" padding="roomy" aria-label="Your ratings are being reviewed" className="flex flex-col gap-3 border-l-4 border-coral">
      <p className="text-ui text-ink">Pacifyco is reviewing your ratings.</p>
      <p className="whitespace-pre-line text-ink">{flag.reason}</p>
      {flag.response ? (
        <>
          <p className="text-small text-muted">
            Your response{flag.responded_at ? `, sent ${formatDate(new Date(flag.responded_at))}` : ""}:
          </p>
          <p className="whitespace-pre-line text-ink">{flag.response}</p>
          <p className="text-small text-muted">We'll tell you what we decide.</p>
        </>
      ) : (
        <>
          <p className="text-ink">
            Please respond by {formatDay(new Date(flag.respond_by))}, {formatTime(new Date(flag.respond_by))}.
          </p>
          <Respond flag={flag} />
        </>
      )}
    </Card>
  );
}

export function SitterReviewsPage() {
  const reviews = useQuery({ queryKey: REVIEWS_KEY, queryFn: () => apiFetch<SitterReviews>("/sitter/reviews") });
  if (reviews.isPending) return <p className="text-muted">Loading…</p>;
  if (reviews.isError) {
    return (
      <p role="alert" className="text-danger">
        We couldn't load your reviews. Please try again.
      </p>
    );
  }
  const data = reviews.data;
  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-4">
      <h1>Your reviews</h1>
      {data.flag && <FlagCard flag={data.flag} />}
      {data.review_count === 0 || data.avg_rating === null ? (
        <EmptyState message="No reviews yet. Families can review you after each booking." />
      ) : (
        <>
          <p className="flex items-center gap-2 text-ink">
            <Stars rating={Math.round(data.avg_rating)} />
            <span>
              {data.avg_rating.toFixed(1)} · {plural(data.review_count, "review", "reviews")}
            </span>
          </p>
          <p className="text-small text-muted">Families see these on your profile, with their first name.</p>
          <Card as="section" padding="roomy">
            <ReviewList reviews={data.reviews} label="Families' reviews" />
          </Card>
        </>
      )}
    </section>
  );
}
