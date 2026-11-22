import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { formatDay } from "../lib/format";
import { Button, Card, Textarea, showToast } from "./ui";

// Reviews (CLAUDE.md 6.11): after a booking where care happened, the parent and the sitter each leave a 1-5
// rating and an optional short review of the other, once, within 14 days. Parents' reviews show on the
// sitter's profile; a sitter's review of a family is seen only by Pacifyco (Reuben, 2026-11-22).

export type MyReview = { rating: number; body: string | null; created_at: string };
export type ReviewState = { mine: MyReview | null; can_review: boolean; open_until: string | null };

export const REVIEW_MAX = 500;

/** Five stars, filled up to the rating; read out as "4 out of 5 stars". */
export function Stars({ rating, size = 18 }: { rating: number; size?: number }) {
  return (
    <span role="img" aria-label={`${rating} out of 5 stars`} className="inline-flex gap-0.5 text-coral-deep">
      {[1, 2, 3, 4, 5].map((value) => (
        <Star
          key={value}
          aria-hidden="true"
          size={size}
          strokeWidth={1.75}
          fill={value <= rating ? "currentColor" : "none"}
        />
      ))}
    </span>
  );
}

function StarPicker({
  legend,
  value,
  onChange,
  error,
}: {
  legend: string;
  value: number;
  onChange: (rating: number) => void;
  error?: string;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-ui text-ink">{legend}</legend>
      <div className="flex gap-1">
        {[1, 2, 3, 4, 5].map((rating) => (
          <label
            key={rating}
            className="cursor-pointer rounded-md p-1 text-coral-deep has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2"
          >
            <input
              type="radio"
              name="rating"
              value={rating}
              checked={value === rating}
              onChange={() => onChange(rating)}
              className="sr-only"
              aria-label={rating === 1 ? "1 star" : `${rating} stars`}
            />
            <Star aria-hidden="true" size={32} strokeWidth={1.75} fill={rating <= value ? "currentColor" : "none"} />
          </label>
        ))}
      </div>
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </fieldset>
  );
}

export function ReviewCard<T extends { review: ReviewState }>({
  path,
  queryKey,
  review,
  question,
  note,
}: {
  path: string;
  queryKey: unknown[];
  review: ReviewState;
  question: string;
  note: string;
}) {
  const queryClient = useQueryClient();
  const [rating, setRating] = useState(0);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | undefined>();
  const send = useMutation({
    mutationFn: () =>
      apiFetch<T>(path, { method: "POST", body: JSON.stringify({ rating, body: body.trim() || null }) }),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKey, updated);
      showToast("Thank you for your review.");
    },
    onError: (failed) => setError(failed instanceof ApiError ? failed.message : "That didn't go through. Please try again."),
  });

  if (review.mine) {
    return (
      <Card as="section" padding="roomy" aria-label="Your review" className="flex flex-col gap-2">
        <p className="text-ink">Your review</p>
        <Stars rating={review.mine.rating} />
        {review.mine.body && <p className="text-ink">{review.mine.body}</p>}
        <p className="text-small text-muted">{note}</p>
      </Card>
    );
  }
  if (!review.can_review) return null;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (rating === 0) return setError("Choose from 1 to 5 stars.");
    setError(undefined);
    send.mutate();
  }

  return (
    <Card as="section" padding="roomy" aria-label="Leave a review">
      <form noValidate onSubmit={submit} className="flex flex-col gap-4">
        <StarPicker legend={question} value={rating} onChange={setRating} error={error} />
        <Textarea
          label="A few words"
          optional
          rows={3}
          maxLength={REVIEW_MAX}
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
        <p className="text-small text-muted">
          {note}
          {review.open_until ? ` You can leave one until ${formatDay(new Date(review.open_until))}.` : ""}
        </p>
        <div>
          <Button type="submit" loading={send.isPending} fullWidthOnPhone={false}>
            Send review
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** A family's review of a sitter, as shown on her profile: the parent's first name only. */
export type PublicReview = { rating: number; body: string | null; author_first_name: string | null; created_at: string };

function monthOf(at: string): string {
  return new Date(at).toLocaleString("en-GB", { month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
}

/** Families' reviews, newest first. */
export function ReviewList({ reviews, label }: { reviews: PublicReview[]; label: string }) {
  return (
    <ul aria-label={label} className="flex flex-col">
      {reviews.map((item, index) => (
        <li key={index} className="flex flex-col gap-1 border-t border-line py-3 first:border-t-0">
          <Stars rating={item.rating} />
          {item.body && <p className="whitespace-pre-line text-ink">{item.body}</p>}
          <p className="text-small text-muted">
            {item.author_first_name ?? "A family"} · {monthOf(item.created_at)}
          </p>
        </li>
      ))}
    </ul>
  );
}
