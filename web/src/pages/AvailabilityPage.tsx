import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { BackLink, Button, Card, EmptyState, Select, TextInput } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { formatBookingTime } from "../lib/format";
import { END_HOURS, START_HOURS, hourLabel, kolkataTime, todayInKolkata } from "../lib/times";

// A sitter's free times (CLAUDE.md 6.4): dated slots she adds and removes (design.md: no weekday
// toggles in v1). Parents can book her only inside these.

type Slot = { id: string; starts_at: string; ends_at: string };

const KEY = ["sitter-availability"];

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}

function AddTimeForm() {
  const queryClient = useQueryClient();
  const [date, setDate] = useState("");
  const [from, setFrom] = useState(9);
  const [until, setUntil] = useState(13);
  const [dateError, setDateError] = useState<string>();

  const add = useMutation({
    mutationFn: (body: { starts_at: string; ends_at: string }) =>
      apiFetch<Slot>("/sitter/availability", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!date) return setDateError("Please choose a day.");
    setDateError(undefined);
    add.mutate({ starts_at: kolkataTime(date, from), ends_at: kolkataTime(date, until) });
  }

  return (
    <Card as="section" padding="roomy" aria-labelledby="add-heading">
      <h2 id="add-heading" className="text-h3">
        Add a free time
      </h2>
      <form onSubmit={submit} className="mt-4 flex flex-col gap-5" noValidate>
        <TextInput
          label="Day"
          type="date"
          min={todayInKolkata()}
          value={date}
          onChange={(event) => setDate(event.target.value)}
          error={dateError}
        />
        <div className="grid gap-5 sm:grid-cols-2">
          <Select label="From" value={from} onChange={(event) => setFrom(Number(event.target.value))}>
            {START_HOURS.map((hour) => (
              <option key={hour} value={hour}>
                {hourLabel(hour)}
              </option>
            ))}
          </Select>
          <Select label="Until" value={until} onChange={(event) => setUntil(Number(event.target.value))}>
            {END_HOURS.map((hour) => (
              <option key={hour} value={hour}>
                {hourLabel(hour)}
              </option>
            ))}
          </Select>
        </div>
        {add.isError && (
          <p role="alert" className="text-small text-danger">
            {add.error instanceof ApiError && add.error.code === "validation_error"
              ? "The end time must be after the start time."
              : errorText(add.error)}
          </p>
        )}
        <Button type="submit" loading={add.isPending} fullWidthOnPhone={false} className="self-start">
          Add this time
        </Button>
      </form>
    </Card>
  );
}

function SlotRow({ slot }: { slot: Slot }) {
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: () => apiFetch<void>(`/sitter/availability/${slot.id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
  const when = formatBookingTime(new Date(slot.starts_at), new Date(slot.ends_at));
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 border-t border-line py-4 first:border-t-0">
      <span className="text-ui">{when}</span>
      <Button
        variant="tertiary"
        loading={remove.isPending}
        aria-label={`Remove ${when}`}
        onClick={() => remove.mutate()}
      >
        Remove
      </Button>
      {remove.isError && (
        <p role="alert" className="w-full text-small text-danger">
          {errorText(remove.error)}
        </p>
      )}
    </li>
  );
}

export function AvailabilityPage() {
  const slots = useQuery({ queryKey: KEY, queryFn: () => apiFetch<Slot[]>("/sitter/availability") });

  return (
    <section className="mx-auto flex max-w-[40rem] flex-col gap-6">
      <BackLink to="/sitter" label="Home" />
      <div className="text-center">
        <h1>Your availability</h1>
        <p className="mt-4 text-muted">Add the times you're free. Families can book you only inside these times.</p>
      </div>
      <AddTimeForm />
      <Card as="section" padding="roomy" aria-labelledby="times-heading">
        <h2 id="times-heading" className="text-h3">
          Your free times
        </h2>
        {slots.isPending && <p className="mt-3 text-muted">Loading…</p>}
        {slots.isError && (
          <p role="alert" className="mt-3 text-danger">
            {errorText(slots.error)}
          </p>
        )}
        {slots.isSuccess &&
          (slots.data.length === 0 ? (
            <div className="mt-3">
              <EmptyState message="No free times yet. Add one above so families can book you." />
            </div>
          ) : (
            <ul className="mt-3">
              {slots.data.map((slot) => (
                <SlotRow key={slot.id} slot={slot} />
              ))}
            </ul>
          ))}
      </Card>
    </section>
  );
}
