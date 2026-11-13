import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { BackLink, Button, ButtonLink, Card, Textarea } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { cx } from "../components/ui/cx";
import { formatDate } from "../lib/format";
import { SitterGate, SitterProgress } from "./SitterSteps";

// Psychology screening (CLAUDE.md section 7 step 5): a handful of multiple-choice and short-answer
// questions. Not auto-scored -- an admin reads the answers later, so this page only has to collect
// them and show where the sitter stands.

type QuestionKind = "multiple_choice" | "short_answer" | "scale";

type Question = {
  id: string;
  order_index: number;
  kind: QuestionKind;
  prompt: string;
  options: string[] | null;
};

type AttemptStatus = "in_progress" | "submitted" | "passed" | "failed";

type Attempt = {
  status: AttemptStatus;
  submitted_at: string | null;
  answers: Record<string, string>;
  /** After a fail, Pacifyco has allowed her to try again (decided 2026-11-08). */
  retake_allowed: boolean;
};

type PsychTest = {
  test_id: string;
  is_placeholder: boolean;
  questions: Question[];
  attempt: Attempt | null;
};

function usePsychTest() {
  return useQuery({ queryKey: ["psych-test"], queryFn: () => apiFetch<PsychTest>("/sitter/psych-test") });
}

// ---------- the form ----------

function QuestionField({
  question,
  value,
  onChange,
}: {
  question: Question;
  value: string;
  onChange: (value: string) => void;
}) {
  // Reuben's screening statements (2026-11-13): pick a number from 1 (least relevant) to 5 (most relevant).
  if (question.kind === "scale") {
    return (
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 text-ui text-ink">{question.prompt}</legend>
        <div className="grid grid-cols-5 gap-2">
          {["1", "2", "3", "4", "5"].map((number) => (
            <label
              key={number}
              className={cx(
                "flex min-h-[44px] cursor-pointer items-center justify-center rounded-pill border text-ui transition-colors duration-200 ease-calm",
                value === number ? "border-ink bg-ink text-surface-default" : "border-strong bg-surface-raised text-ink",
              )}
            >
              <input
                type="radio"
                name={`question-${question.id}`}
                value={number}
                checked={value === number}
                onChange={() => onChange(number)}
                className="sr-only"
              />
              {number}
            </label>
          ))}
        </div>
        <p className="flex justify-between text-caption text-muted">
          <span>1 = least relevant</span>
          <span>5 = most relevant</span>
        </p>
      </fieldset>
    );
  }
  if (question.kind === "short_answer") {
    return (
      <Textarea label={question.prompt} value={value} onChange={(event) => onChange(event.target.value)} rows={3} />
    );
  }
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 text-ui text-ink">{question.prompt}</legend>
      {(question.options ?? []).map((option) => (
        <label
          key={option}
          className="flex cursor-pointer items-start gap-3 rounded-md border border-strong bg-surface-raised px-4 py-3 text-body text-ink"
        >
          <input
            type="radio"
            name={`question-${question.id}`}
            checked={value === option}
            onChange={() => onChange(option)}
            className="mt-1 size-5 shrink-0 cursor-pointer accent-[var(--accent-coral)]"
          />
          <span>{option}</span>
        </label>
      ))}
    </fieldset>
  );
}

// One question at a time, with Back to the question before (from the first question, back to the
// application) and Next. Answers are sent together when she submits on the last question.
function PsychTestForm({ questions, initial }: { questions: Question[]; initial: Record<string, string> }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [answers, setAnswers] = useState<Record<string, string>>(initial);
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string>();

  const submit = useMutation({
    mutationFn: async () => {
      await apiFetch("/sitter/psych-test/answers", {
        method: "PUT",
        body: JSON.stringify({
          answers: questions.map((question) => ({ question_id: question.id, answer_text: answers[question.id] ?? "" })),
        }),
      });
      return apiFetch<Attempt>("/sitter/psych-test/submit", { method: "POST" });
    },
    // The screening is the last page of the application: swap the form for the "submitted" confirmation.
    onSuccess: (attempt) => {
      queryClient.setQueryData<PsychTest>(["psych-test"], (test) => (test ? { ...test, attempt } : test));
      queryClient.invalidateQueries({ queryKey: ["checklist"] });
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again."),
  });

  const question = questions[index];
  if (!question) return null;
  const isLast = index === questions.length - 1;

  function goBack() {
    setError(undefined);
    if (index === 0) navigate("/sitter/application");
    else setIndex(index - 1);
  }

  function goNext() {
    if (!(answers[question!.id] ?? "").trim()) {
      setError("Please answer this question to continue.");
      return;
    }
    setError(undefined);
    if (isLast) submit.mutate();
    else setIndex(index + 1);
  }

  return (
    <div className="flex flex-col gap-6">
      <div key={question.id}>
        <p className="mb-2 text-small text-muted">
          Question {index + 1} of {questions.length}
        </p>
        <QuestionField
          question={question}
          value={answers[question.id] ?? ""}
          onChange={(value) => setAnswers((current) => ({ ...current, [question.id]: value }))}
        />
      </div>
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="secondary" fullWidthOnPhone={false} disabled={submit.isPending} onClick={goBack}>
          ← Back
        </Button>
        <Button type="button" fullWidthOnPhone={false} loading={submit.isPending} onClick={goNext}>
          {isLast ? "Submit" : "Next"}
        </Button>
      </div>
    </div>
  );
}

// ---------- status views ----------

function SubmittedView({ submittedAt }: { submittedAt: string | null }) {
  return (
    <div role="status" className="flex flex-col items-start gap-3 rounded-lg bg-surface-sunken p-5">
      <p className="text-h3 text-ink">Your application is submitted.</p>
      <p className="text-ink">
        {submittedAt ? `We received it on ${formatDate(new Date(submittedAt))}. ` : ""}An admin will look over your
        answers and the rest of your application.
      </p>
      <p className="text-small text-muted">We'll let you know once it's reviewed.</p>
      <ButtonLink to="/sitter/profile" variant="secondary">
        Go to your profile
      </ButtonLink>
    </div>
  );
}

function PassedView() {
  return (
    <div className="rounded-lg bg-surface-sunken p-5">
      <p className="text-ink">You've passed the psychology screening.</p>
    </div>
  );
}

function FailedView({ retakeAllowed, onRetake }: { retakeAllowed: boolean; onRetake: () => void }) {
  if (!retakeAllowed) {
    return (
      <div className="rounded-lg bg-surface-sunken p-5">
        <p className="text-ink">
          You didn't pass this time. Pacifyco will be in touch about whether you can take the screening again.
        </p>
      </div>
    );
  }
  return (
    <div className="flex flex-col items-start gap-4 rounded-lg bg-surface-sunken p-5">
      <p className="text-ink">You didn't pass this time, and Pacifyco has said you can try again.</p>
      <Button variant="secondary" onClick={onRetake}>
        Try again
      </Button>
    </div>
  );
}

// ---------- the page ----------

export function PsychTestPage() {
  const test = usePsychTest();
  const [retaking, setRetaking] = useState(false);
  const attempt = test.data?.attempt;

  // Once she's submitted, only the confirmation shows: no heading, intro or links around it (Reuben,
  // 2026-11-13).
  if (attempt?.status === "submitted") {
    return (
      <article className="mx-auto max-w-[62ch]">
        <SubmittedView submittedAt={attempt.submitted_at} />
      </article>
    );
  }

  return (
    <article className="mx-auto max-w-[62ch]">
      <div className="mb-4">
        <BackLink to="/sitter/application" label="Your application" />
      </div>
      <h1>Psychology screening</h1>
      <p className="mt-2 text-muted">
        A few questions so we can get to know how you think about caring for children.
      </p>

      <div className="mt-6">
        <SitterProgress step="psych_test" />
      </div>
      {/* The last of her eight steps: it opens once the others are filled in. */}
      <div className="mt-4">
        <SitterGate step="psych_test">
          <Card as="section" padding="roomy">
            {test.isPending && <p className="text-muted">Loading…</p>}
            {test.isError && <p className="text-muted">{test.error.message}</p>}
            {test.data &&
              (() => {
                const { questions } = test.data;
                if (attempt && attempt.status === "passed") return <PassedView />;
                if (attempt && attempt.status === "failed" && !retaking) {
                  return <FailedView retakeAllowed={attempt.retake_allowed} onRetake={() => setRetaking(true)} />;
                }
                return <PsychTestForm questions={questions} initial={retaking ? {} : attempt?.answers ?? {}} />;
              })()}
          </Card>
        </SitterGate>
      </div>

      <div className="mt-6">
        <ButtonLink to="/sitter/application" variant="secondary">
          Back to your application
        </ButtonLink>
      </div>
    </article>
  );
}
