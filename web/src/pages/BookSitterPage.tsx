import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router";
import {
  BackLink,
  Button,
  ButtonLink,
  Card,
  Checkbox,
  EmptyState,
  Select,
  TextInput,
  Textarea,
  buttonClasses,
  showToast,
} from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { formatDay, formatTime, joinNames, plural } from "../lib/format";
import { hourlyPaise, rupees, type Price } from "../lib/prices";
import { monthsOld } from "../lib/sitterLists";
import { dayLabel, hourLabel, kolkataTime, todayInKolkata } from "../lib/times";
import { firstNameOf } from "./FindSittersPage";

// "Book this sitter" (CLAUDE.md 6.1 and 6.4; phase 6). The parent picks a day and time from her free
// times, how long, which children, bath time and the camera declaration, and sees the price as they go.
// Her rate only, never her plan's name (Reuben, 2026-11-17). Bookings start 4+ hours from now; the API
// sends only times that can be booked and checks everything again.

type BookableTime = { starts_at: string; ends_at: string };

type BookingOptions = {
  price: Price;
  bath_time_allowed: boolean;
  times: BookableTime[];
  first_booking: boolean;
};

type Child = { id: string; name: string; date_of_birth: string };

export type Booking = {
  id: string;
  sitter_id: string;
  sitter_name: string | null;
  starts_at: string;
  ends_at: string;
  hours: number;
  children: string[];
  price_paise: number;
  bath_time: boolean;
  cameras_on: boolean;
  camera_locations: string | null;
  status: string;
  pay_by: string;
  /** How to pay by UPI: only while it waits for payment and Pacifyco's UPI ID is set. */
  pay_by_upi: PayByUpi | null;
  /** The latest payment the parent sent for it. */
  payment: Payment | null;
};

type PayByUpi = { upi_id: string; payee_name: string; amount_paise: number; note: string; upi_link: string };
type Payment = {
  status: "pending" | "confirmed" | "rejected";
  upi_reference: string | null;
  sent_at: string;
  rejection_reason: string | null;
};

const HOUR_MS = 60 * 60 * 1000;
const PAYMENT_DEADLINE_HOURS = 3; // unpaid bookings are cancelled 3 hours before the start (6.1)

/** One free stretch on one India day, as hours after that day's midnight (24 is the end of the day). */
type Window = { day: string; start: number; end: number };

/** The API splits her times at midnight, so each stretch belongs to one day. */
export function windowsFrom(times: BookableTime[]): Window[] {
  return times.map((time) => {
    const day = todayInKolkata(new Date(time.starts_at));
    const midnight = Date.parse(kolkataTime(day, 0));
    return {
      day,
      start: Math.round((Date.parse(time.starts_at) - midnight) / HOUR_MS),
      end: Math.round((Date.parse(time.ends_at) - midnight) / HOUR_MS),
    };
  });
}

/** Whole months old on a given India day ("2026-11-21"), as the API counts them. */
function monthsOldOn(dateOfBirth: string, day: string): number {
  return monthsOld(dateOfBirth, new Date(`${day}T12:00:00Z`));
}

const MIN_AGE_MONTHS = 18; // 6.4

type Errors = Partial<Record<"time" | "children" | "cameras" | "camera_locations", string>>;

function BookingForm({
  sitterId,
  firstName,
  options,
  children,
}: {
  sitterId: string;
  firstName: string;
  options: BookingOptions;
  children: Child[];
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const windows = useMemo(() => windowsFrom(options.times), [options.times]);
  const days = [...new Set(windows.map((window) => window.day))];
  const [day, setDay] = useState(days[0] ?? "");
  const [start, setStart] = useState<number | null>(null);
  const [hours, setHours] = useState(1);
  const eligible = (child: Child) => !day || monthsOldOn(child.date_of_birth, day) >= MIN_AGE_MONTHS;
  // A booking starts as one child (decided 2026-11-09); the parent adds anyone else who'll be there.
  const [childIds, setChildIds] = useState<string[]>(() => {
    const first = children.find(eligible);
    return first ? [first.id] : [];
  });
  const [bathTime, setBathTime] = useState(false);
  const [cameras, setCameras] = useState<"" | "yes" | "no">("");
  const [cameraLocations, setCameraLocations] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string>();

  const dayWindows = windows.filter((window) => window.day === day);
  const starts = dayWindows.flatMap((window) =>
    Array.from({ length: window.end - window.start }, (_, index) => window.start + index),
  );
  const chosenStart = start !== null && starts.includes(start) ? start : (starts[0] ?? null);
  const window = dayWindows.find((item) => chosenStart !== null && item.start <= chosenStart && chosenStart < item.end);
  const maxHours = window && chosenStart !== null ? window.end - chosenStart : 1;
  const chosenHours = Math.min(hours, maxHours);
  const chosenChildren = childIds.filter((id) => children.some((child) => child.id === id && eligible(child)));
  const perHour = hourlyPaise(options.price, Math.max(chosenChildren.length, 1));
  const total = perHour * chosenHours;
  const startsAt = chosenStart !== null && day ? new Date(kolkataTime(day, chosenStart)) : null;
  const payBy = startsAt ? new Date(startsAt.getTime() - PAYMENT_DEADLINE_HOURS * HOUR_MS) : null;

  const book = useMutation({
    mutationFn: (body: object) => apiFetch<Booking>("/parent/bookings", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: async (booking) => {
      queryClient.setQueryData(["booking", booking.id], booking);
      await queryClient.invalidateQueries({ queryKey: ["booking-options", sitterId] });
      navigate(`/parent/bookings/${booking.id}`);
    },
    onError: async (error) => {
      if (error instanceof ApiError && (error.code === "not_free" || error.code === "too_soon")) {
        await queryClient.invalidateQueries({ queryKey: ["booking-options", sitterId] });
      }
      setFormError(error instanceof ApiError ? error.message : "Something went wrong. Please try again.");
    },
  });

  function toggleChild(id: string, ticked: boolean) {
    if (options.price.one_child_only) setChildIds(ticked ? [id] : []);
    else setChildIds((current) => (ticked ? [...current, id] : current.filter((item) => item !== id)));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const found: Errors = {};
    if (chosenStart === null) found.time = "Please choose a time.";
    if (!chosenChildren.length) found.children = `Please choose who ${firstName} will be looking after.`;
    if (!cameras) found.cameras = "Please tell us whether cameras are on at home.";
    if (cameras === "yes" && !cameraLocations.trim()) found.camera_locations = "Please tell us where the cameras are.";
    setErrors(found);
    setFormError(undefined);
    if (Object.keys(found).length || startsAt === null) return;
    book.mutate({
      sitter_id: sitterId,
      starts_at: startsAt.toISOString(),
      hours: chosenHours,
      child_ids: chosenChildren,
      bath_time: options.bath_time_allowed && bathTime,
      cameras_on: cameras === "yes",
      camera_locations: cameras === "yes" ? cameraLocations.trim() : null,
    });
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-6">
      {options.first_booking && (
        <p className="rounded-lg bg-surface-sunken p-5 text-small text-ink">
          New to {firstName}? Start with a 1-hour booking while you're at home, to see how {firstName} gets on with
          your family.
        </p>
      )}

      <Card as="section" padding="roomy" aria-labelledby="when-heading" className="flex flex-col gap-5">
        <h2 id="when-heading" className="text-h3">
          When
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <Select
            label="Day"
            value={day}
            onChange={(event) => {
              setDay(event.target.value);
              setStart(null);
            }}
          >
            {days.map((item) => (
              <option key={item} value={item}>
                {dayLabel(item)}
              </option>
            ))}
          </Select>
          <Select
            label="Start"
            value={chosenStart ?? ""}
            error={errors.time}
            onChange={(event) => setStart(Number(event.target.value))}
          >
            {starts.map((hour) => (
              <option key={hour} value={hour}>
                {hourLabel(hour)}
              </option>
            ))}
          </Select>
          <Select label="How long" value={chosenHours} onChange={(event) => setHours(Number(event.target.value))}>
            {Array.from({ length: maxHours }, (_, index) => index + 1).map((count) => (
              <option key={count} value={count}>
                {plural(count, "hour", "hours")}
              </option>
            ))}
          </Select>
        </div>
        {startsAt && (
          <p className="text-small text-muted">
            {formatDay(startsAt)} · {formatTime(startsAt)} –{" "}
            {formatTime(new Date(startsAt.getTime() + chosenHours * HOUR_MS))}
          </p>
        )}
      </Card>

      <Card as="section" padding="roomy" aria-labelledby="who-heading" className="flex flex-col gap-4">
        <h2 id="who-heading" className="text-h3">
          Who {firstName} is looking after
        </h2>
        {options.price.one_child_only && (
          <p className="-mt-2 text-small text-muted">{firstName} looks after one child at a time.</p>
        )}
        <fieldset className="flex flex-col gap-3" aria-describedby={errors.children ? "children-error" : undefined}>
          <legend className="sr-only">Children</legend>
          {children.map((child) =>
            eligible(child) ? (
              <Checkbox
                key={child.id}
                label={child.name}
                checked={childIds.includes(child.id)}
                onChange={(event) => toggleChild(child.id, event.target.checked)}
              />
            ) : (
              <Checkbox
                key={child.id}
                disabled
                readOnly
                checked={false}
                label={
                  <>
                    {child.name} <span className="text-muted">· Pacifyco looks after children from 18 months</span>
                  </>
                }
              />
            ),
          )}
        </fieldset>
        {errors.children && (
          <p id="children-error" role="alert" className="text-small text-danger">
            {errors.children}
          </p>
        )}
        {options.bath_time_allowed && (
          <Checkbox
            label="Bath time"
            checked={bathTime}
            onChange={(event) => setBathTime(event.target.checked)}
          />
        )}
      </Card>

      <Card as="section" padding="roomy" aria-labelledby="home-heading" className="flex flex-col gap-4">
        <h2 id="home-heading" className="text-h3">
          Cameras at home
        </h2>
        <fieldset className="flex flex-col gap-3" aria-describedby={errors.cameras ? "cameras-error" : undefined}>
          <legend className="text-ui text-ink">Will any cameras be on while {firstName} is there?</legend>
          {(
            [
              ["no", "No"],
              ["yes", "Yes"],
            ] as const
          ).map(([value, label]) => (
            <label key={value} className="flex cursor-pointer items-center gap-3 text-body text-ink">
              <input
                type="radio"
                name="cameras"
                value={value}
                checked={cameras === value}
                onChange={() => setCameras(value)}
                className="size-5 cursor-pointer accent-[var(--accent-coral)]"
              />
              {label}
            </label>
          ))}
        </fieldset>
        {errors.cameras && (
          <p id="cameras-error" role="alert" className="text-small text-danger">
            {errors.cameras}
          </p>
        )}
        {cameras === "yes" && (
          <Textarea
            label="Where are they?"
            hint={`${firstName} sees this before the booking. Cameras must never be in bathrooms or changing areas.`}
            rows={2}
            maxLength={500}
            value={cameraLocations}
            error={errors.camera_locations}
            onChange={(event) => setCameraLocations(event.target.value)}
          />
        )}
      </Card>

      <Card as="section" padding="roomy" aria-labelledby="price-heading" className="flex flex-col gap-3">
        <h2 id="price-heading" className="text-h3">
          Price
        </h2>
        <p className="text-h2 text-ink" aria-live="polite">
          {rupees(total)}
        </p>
        <p className="text-small text-muted">
          {plural(chosenHours, "hour", "hours")} × {rupees(perHour)} an hour
          {chosenChildren.length > 1 && ` for ${plural(chosenChildren.length, "child", "children")}`}
        </p>
        {payBy && (
          <p className="text-small text-ink">
            You'll pay by UPI on the next page. Please pay by {formatDay(payBy)}, {formatTime(payBy)}, 3 hours
            before it starts, or the booking is cancelled.
          </p>
        )}
        {formError && (
          <p role="alert" className="text-small text-danger">
            {formError}
          </p>
        )}
        <Button type="submit" arrow loading={book.isPending}>
          Confirm this time
        </Button>
      </Card>
    </form>
  );
}

export function BookSitterPage() {
  const { sitterId = "" } = useParams();
  const sitter = useQuery({
    queryKey: ["sitter-profile", sitterId],
    queryFn: () => apiFetch<{ full_name: string | null }>(`/parent/sitters/${sitterId}`),
  });
  const options = useQuery({
    queryKey: ["booking-options", sitterId],
    queryFn: () => apiFetch<BookingOptions>(`/parent/sitters/${sitterId}/booking-options`),
  });
  const children = useQuery({ queryKey: ["children"], queryFn: () => apiFetch<Child[]>("/parent/children") });

  if (sitter.isPending || options.isPending || children.isPending) {
    return <p className="text-center text-muted">Loading…</p>;
  }
  const failed = sitter.error ?? options.error ?? children.error;
  if (failed) {
    const code = failed instanceof ApiError ? failed.code : null;
    return (
      <section className="mx-auto max-w-[40rem]">
        <EmptyState
          message={
            code === "profile_unfinished"
              ? "Finish your profile first, then you can book a sitter."
              : code === "not_found"
                ? "This sitter isn't available right now."
                : "Something went wrong. Please try again."
          }
          action={
            <ButtonLink to={code === "profile_unfinished" ? "/parent/profile" : "/parent/sitters"} arrow>
              {code === "profile_unfinished" ? "Finish your profile" : "Find a sitter"}
            </ButtonLink>
          }
        />
      </section>
    );
  }

  const firstName = firstNameOf(sitter.data?.full_name ?? null);
  const kids = children.data ?? [];
  return (
    <article className="mx-auto flex max-w-[40rem] flex-col gap-6">
      <BackLink to={`/parent/sitters/${sitterId}`} label={`${firstName}'s profile`} />
      <h1>Choose a time with {firstName}</h1>
      {options.data!.times.length === 0 ? (
        <EmptyState
          message={`${firstName} has no free times in the next two weeks that start at least 4 hours from now.`}
          action={<ButtonLink to="/parent/sitters">Find another sitter</ButtonLink>}
        />
      ) : kids.length === 0 ? (
        <EmptyState
          message="Add your children to your profile first, so your sitter knows who she's caring for."
          action={<ButtonLink to="/parent/family">Your children</ButtonLink>}
        />
      ) : (
        <BookingForm sitterId={sitterId} firstName={firstName} options={options.data!} children={kids} />
      )}
    </article>
  );
}

/** The booking, once made: what was booked, and paying for it by UPI (6.1). */
export function BookingPage() {
  const { bookingId = "" } = useParams();
  const booking = useQuery({
    queryKey: ["booking", bookingId],
    queryFn: () => apiFetch<Booking>(`/parent/bookings/${bookingId}`),
  });
  if (booking.isPending) return <p className="text-center text-muted">Loading…</p>;
  if (booking.isError) {
    return (
      <section className="mx-auto max-w-[40rem]">
        <EmptyState
          message="We couldn't find that booking."
          action={<ButtonLink to="/parent/sitters">Find a sitter</ButtonLink>}
        />
      </section>
    );
  }
  const data = booking.data;
  const firstName = firstNameOf(data.sitter_name);
  const startsAt = new Date(data.starts_at);
  const waiting = data.status === "pending_payment";
  return (
    <article className="mx-auto flex max-w-[40rem] flex-col gap-6">
      <BackLink to={`/parent/sitters/${data.sitter_id}`} label={`${firstName}'s profile`} />
      <h1>Your booking with {firstName}</h1>
      <Card as="section" padding="roomy" className="flex flex-col gap-3">
        <p className="text-eyebrow text-muted uppercase">{statusLabel(data.status)}</p>
        <p className="text-h3 text-ink">
          {formatDay(startsAt)} · {formatTime(startsAt)} – {formatTime(new Date(data.ends_at))}
        </p>
        <p className="text-ink">
          {firstName} is looking after {joinNames(data.children)} at home
          {data.bath_time ? ", with bath time" : ""}.
        </p>
        <p className="text-small text-muted">
          {plural(data.hours, "hour", "hours")} · {rupees(data.price_paise)}
        </p>
      </Card>
      {waiting && <PaymentCard booking={data} />}
      {data.status === "awaiting_verification" && (
        <Card as="section" padding="roomy" className="flex flex-col gap-3">
          <p className="text-ink">
            Thank you, we've received your payment and kept this time with {firstName} for you. The booking is
            confirmed once Pacifyco has checked every child's birth certificate.
          </p>
        </Card>
      )}
      {data.status === "confirmed" && (
        <Card as="section" padding="roomy" className="flex flex-col gap-3">
          <p className="text-ink">Your booking is confirmed and paid.</p>
        </Card>
      )}
      {data.status === "cancelled_unpaid" && (
        <CancelledCard sitterId={data.sitter_id}>
          This booking was cancelled because it wasn't paid by {formatDay(new Date(data.pay_by))},{" "}
          {formatTime(new Date(data.pay_by))}. You haven't been charged.
        </CancelledCard>
      )}
      {data.status === "cancelled_slot_taken" && (
        <CancelledCard sitterId={data.sitter_id}>
          Another booking for this time with {firstName} was paid for first, so this one was cancelled.
          {data.payment ? " If you've paid, Pacifyco will refund you." : ""}
        </CancelledCard>
      )}
    </article>
  );
}

function statusLabel(status: string): string {
  if (status === "pending_payment") return "Waiting for payment";
  if (status === "awaiting_verification") return "Paid";
  if (status === "confirmed") return "Confirmed";
  if (status.startsWith("cancelled")) return "Cancelled";
  return "Booking";
}

/** A booking Pacifyco cancelled before it was paid for (6.1 and 6.4), and a way to book again. */
function CancelledCard({ sitterId, children }: { sitterId: string; children: ReactNode }) {
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3">
      <p className="text-ink">{children}</p>
      <div>
        <ButtonLink to={`/parent/sitters/${sitterId}/book`}>Choose another time</ButtonLink>
      </div>
    </Card>
  );
}

const CHECKING_NOTE =
  "The booking is confirmed once Pacifyco has checked your payment and every child on it is verified.";

/** Pay by UPI, then send the 12-digit UPI reference; or, once sent, that it's being checked. */
function PaymentCard({ booking }: { booking: Booking }) {
  const payBy = new Date(booking.pay_by);
  const payment = booking.payment;

  if (payment?.status === "pending") {
    return (
      <Card as="section" padding="roomy" className="flex flex-col gap-3">
        <h2 className="text-h3">Payment sent</h2>
        <p className="text-ink">
          Thank you. We're checking your payment of {rupees(booking.price_paise)} (UPI reference{" "}
          {payment.upi_reference}).
        </p>
        <p className="text-small text-muted">{CHECKING_NOTE}</p>
      </Card>
    );
  }

  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-4">
      <h2 className="text-h3">Pay {rupees(booking.price_paise)} by UPI</h2>
      {payment?.status === "rejected" && (
        <p role="alert" className="text-danger">
          We couldn't confirm your payment: {payment.rejection_reason} Please check the UPI reference and send it
          again.
        </p>
      )}
      <p className="text-ink">
        Please pay by {formatDay(payBy)}, {formatTime(payBy)}. If it isn't paid by then, the booking is cancelled.
      </p>
      {booking.pay_by_upi ? (
        <>
          <UpiDetails upi={booking.pay_by_upi} />
          <ReferenceForm bookingId={booking.id} />
        </>
      ) : (
        <p className="text-ink">We can't take payments just yet. Please check back soon.</p>
      )}
      <p className="text-small text-muted">{CHECKING_NOTE}</p>
    </Card>
  );
}

function UpiDetails({ upi }: { upi: PayByUpi }) {
  const qr = useQrCode(upi.upi_link);

  async function copy() {
    try {
      await navigator.clipboard.writeText(upi.upi_id);
      showToast("UPI ID copied");
    } catch {
      showToast("Couldn't copy. Please select the UPI ID and copy it.");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <ol className="flex list-decimal flex-col gap-1 pl-5 text-ink">
        <li>
          Pay {rupees(upi.amount_paise)} to {upi.payee_name} from any UPI app.
        </li>
        <li>Copy the 12-digit UPI reference from the payment details and enter it below.</li>
      </ol>
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-ink">
          <span className="text-small text-muted">UPI ID </span>
          <span className="font-semibold select-all">{upi.upi_id}</span>
        </p>
        <Button variant="secondary" fullWidthOnPhone={false} onClick={() => void copy()}>
          Copy
        </Button>
      </div>
      <a href={upi.upi_link} className={buttonClasses({ variant: "secondary" })}>
        Pay in a UPI app
      </a>
      {qr && (
        <figure className="flex flex-col items-center gap-2">
          <img
            src={qr}
            alt={`QR code to pay ${rupees(upi.amount_paise)} to ${upi.payee_name}`}
            width={192}
            height={192}
            className="rounded-lg bg-white p-2"
          />
          <figcaption className="text-small text-muted">On a computer? Scan this with your phone.</figcaption>
        </figure>
      )}
      <p className="text-small text-muted">Note on the payment: {upi.note}</p>
    </div>
  );
}

/** The `upi://pay` link as a QR code image (an SVG, so it works without a canvas). */
function useQrCode(link: string): string | null {
  const [image, setImage] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    QRCode.toString(link, { type: "svg", margin: 1, errorCorrectionLevel: "M" })
      .then((svg) => {
        if (current) setImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`);
      })
      .catch(() => {
        if (current) setImage(null);
      });
    return () => {
      current = false;
    };
  }, [link]);
  return image;
}

function ReferenceForm({ bookingId }: { bookingId: string }) {
  const queryClient = useQueryClient();
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const send = useMutation({
    mutationFn: (upi_reference: string) =>
      apiFetch<Booking>(`/parent/bookings/${bookingId}/payment`, {
        method: "POST",
        body: JSON.stringify({ upi_reference }),
      }),
    onSuccess: (booking) => {
      queryClient.setQueryData(["booking", bookingId], booking);
      showToast("Payment sent. We'll check it soon.");
    },
    onError: async (failed) => {
      setError(failed instanceof ApiError ? failed.message : "Something went wrong. Please try again.");
      if (failed instanceof ApiError && failed.status === 409) {
        await queryClient.invalidateQueries({ queryKey: ["booking", bookingId] });
      }
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const digits = reference.replace(/\s/g, "");
    if (!/^\d{12}$/.test(digits)) {
      setError("Please enter the 12-digit UPI reference from your UPI app.");
      return;
    }
    setError(null);
    send.mutate(digits);
  }

  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-3">
      <TextInput
        label="UPI reference"
        hint="12 digits. Your UPI app may call it the UTR or UPI transaction ID."
        inputMode="numeric"
        autoComplete="off"
        maxLength={16}
        value={reference}
        error={error ?? undefined}
        onChange={(event) => setReference(event.target.value)}
      />
      <div>
        <Button type="submit" arrow loading={send.isPending}>
          Send the reference
        </Button>
      </div>
    </form>
  );
}
