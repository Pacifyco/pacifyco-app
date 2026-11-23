import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { BackLink, Button, ButtonLink, Card, Checkbox, EmptyState, TextInput, showToast } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { formatBookingTime, formatMobile } from "../lib/format";
import { rupees } from "../lib/prices";
import { todayInKolkata } from "../lib/times";
import { outingText, sitterBookingLine, sitterStatusText, type SitterBookingItem } from "./SitterBookingsPage";
import { BookingHelp, ComplaintLink, type BookingIncident } from "../components/BookingHelp";
import { ReviewCard, type ReviewState } from "../components/ReviewCard";
import { answerByText } from "./SitterRequestsPage";
import { MAN_HOME_FEE_PAISE, SHOW_UP_FEE_PER_HOUR_PAISE, minutesLeft, underWay, type BookingReport } from "../lib/reports";
import { type OvertimeRequest } from "../lib/overtime";

// One of the sitter's requests or bookings (CLAUDE.md 6.4 and 6.11): the children's care notes (medicine
// instructions go in the medical notes, 6.11), bath time, the camera answer, the area and her pay; on a
// request, Accept and Decline (Reuben, 2026-11-19). The home address and the family's emergency contact
// show only once it's confirmed, while it's ahead. Never the price or the plan's name.

type BookingChild = {
  name: string;
  age_months: number;
  allergies: string | null;
  medical_notes: string | null;
  routines: string | null;
};

export type SitterBookingDetail = SitterBookingItem & {
  children_details: BookingChild[];
  address: string | null;
  pin_code: string | null;
  emergency_contact: { name: string; relationship: string; phone: string } | null;
  report: BookingReport | null;
  buttons_open: boolean; // Emergency and Issues (6.9)
  incident: BookingIncident | null;
  checked_in_at: string | null; // (6.7)
  checked_out_at: string | null;
  codes_locked: boolean;
  overtime: OvertimeRequest | null; // (6.8)
  review: ReviewState; // her review of the family; only Pacifyco sees it (6.11)
};

/** "18 months", "2 years", "5 years". */
export function ageText(months: number): string {
  if (months < 24) return `${months} months`;
  return `${Math.floor(months / 12)} years`;
}

function Note({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex flex-col">
      <dt className="text-small text-muted">{label}</dt>
      <dd className="text-ink">{value?.trim() ? value : "None given"}</dd>
    </div>
  );
}

/** Accept or decline a request: she answers before the family pays (6.4). */
function Answer({ booking }: { booking: SitterBookingDetail }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const answer = useMutation({
    mutationFn: (how: "accept" | "decline") =>
      apiFetch<SitterBookingDetail>(`/sitter/bookings/${booking.id}/${how}`, { method: "POST" }),
    onSuccess: (updated, how) => {
      queryClient.setQueryData(["sitter", "booking", booking.id], updated);
      void queryClient.invalidateQueries({ queryKey: ["sitter"] });
      showToast(how === "accept" ? "Accepted. We've asked the family to pay." : "Declined. We've told the family.");
    },
    onError: (failed) => {
      setError(failed instanceof ApiError ? failed.message : "We couldn't send your answer. Please try again.");
      void queryClient.invalidateQueries({ queryKey: ["sitter"] });
    },
  });
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3">
      <p className="text-ui text-coral-deep">{answerByText(booking)}</p>
      <p className="text-ink">
        Can you do this booking? Once you accept, the time is kept for this family while they pay. You'll see
        their address and emergency contact once they've paid.
      </p>
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button arrow loading={answer.isPending && answer.variables === "accept"} onClick={() => answer.mutate("accept")}>
          Accept
        </Button>
        <Button
          variant="secondary"
          loading={answer.isPending && answer.variables === "decline"}
          onClick={() => answer.mutate("decline")}
        >
          Decline
        </Button>
      </div>
    </Card>
  );
}

/** A family's overtime request (6.8): accept or decline once you've agreed it between you. Nothing is
 * charged now; it's worked out at check-out. */
function OvertimeAnswer({ booking }: { booking: SitterBookingDetail }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const requestId = booking.overtime!.id;
  const answer = useMutation({
    mutationFn: (how: "accept" | "decline") =>
      apiFetch<SitterBookingDetail>(`/sitter/overtime-requests/${requestId}/${how}`, { method: "POST" }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["sitter", "booking", booking.id], updated);
      showToast("Thanks. We've told the family.");
    },
    onError: (failed) =>
      setError(failed instanceof ApiError ? failed.message : "We couldn't send your answer. Please try again."),
  });
  const hours = booking.overtime!.hours;
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3">
      <p className="text-ink">
        The family has asked if you can stay {hours === 1 ? "1 more hour" : `${hours} more hours`}. Only accept once
        you've agreed it between you.
      </p>
      <p className="text-small text-muted">Nothing is charged now; it's worked out when you check out.</p>
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button loading={answer.isPending && answer.variables === "accept"} onClick={() => answer.mutate("accept")}>
          Accept
        </Button>
        <Button
          variant="secondary"
          loading={answer.isPending && answer.variables === "decline"}
          onClick={() => answer.mutate("decline")}
        >
          Decline
        </Button>
      </div>
    </Card>
  );
}

/** No one's home (6.5): she reports it, and may leave after 20 minutes if no parent responds. */
function NoOneHome({ booking }: { booking: SitterBookingDetail }) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [noChildAlone, setNoChildAlone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const report = useMutation({
    mutationFn: () =>
      apiFetch<SitterBookingDetail>(`/sitter/bookings/${booking.id}/parent-not-home`, {
        method: "POST",
        body: JSON.stringify({ no_child_alone: noChildAlone }),
      }),
    onSuccess: (updated) => queryClient.setQueryData(["sitter", "booking", booking.id], updated),
    onError: (failed) => setError(failed instanceof ApiError ? failed.message : "That didn't go through. Please try again."),
  });
  if (!asking) {
    return (
      <div>
        <Button variant="secondary" fullWidthOnPhone={false} onClick={() => setAsking(true)}>
          No one's home
        </Button>
      </div>
    );
  }
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3">
      <p className="text-ink">
        Call the parent first. If a child is at home without an adult, don't leave: stay with them, call the parent
        and Pacifyco on +91 8848873841, and call 112 if you need help.
      </p>
      <Checkbox
        label="No child is at home without an adult"
        checked={noChildAlone}
        onChange={(event) => setNoChildAlone(event.target.checked)}
      />
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button
          variant="secondary"
          loading={report.isPending}
          disabled={!noChildAlone}
          onClick={() => report.mutate()}
        >
          Tell Pacifyco no one's home
        </Button>
        <Button variant="tertiary" onClick={() => setAsking(false)}>
          Not now
        </Button>
      </div>
    </Card>
  );
}

/** The only adult at home is a man: she may decline on the spot (6.5; decided 2026-11-12). */
function OnlyManHome({ booking }: { booking: SitterBookingDetail }) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState(false);
  const report = useMutation({
    mutationFn: () =>
      apiFetch<SitterBookingDetail>(`/sitter/bookings/${booking.id}/only-man-home`, { method: "POST" }),
    onSuccess: (updated) => queryClient.setQueryData(["sitter", "booking", booking.id], updated),
  });
  if (!asking) {
    return (
      <div>
        <Button variant="secondary" fullWidthOnPhone={false} onClick={() => setAsking(true)}>
          Only a man is at home
        </Button>
      </div>
    );
  }
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3">
      <p className="text-ink">
        For your safety you may decline this booking. Make sure the children are with him, then leave. You won't
        get a strike, and once Pacifyco confirms you'll be paid {rupees(MAN_HOME_FEE_PAISE)}.
      </p>
      {report.isError && (
        <p role="alert" className="text-small text-danger">
          {report.error instanceof ApiError ? report.error.message : "That didn't go through. Please try again."}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" loading={report.isPending} onClick={() => report.mutate()}>
          Decline this booking
        </Button>
        <Button variant="tertiary" onClick={() => setAsking(false)}>
          Not now
        </Button>
      </div>
    </Card>
  );
}

/** A child on the booking is under 18 months, which should never happen (6.5). */
function UnderAge({ booking }: { booking: SitterBookingDetail }) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [adultWithChild, setAdultWithChild] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const report = useMutation({
    mutationFn: () =>
      apiFetch<SitterBookingDetail>(`/sitter/bookings/${booking.id}/under-18-months`, {
        method: "POST",
        body: JSON.stringify({ adult_with_child: adultWithChild }),
      }),
    onSuccess: (updated) => queryClient.setQueryData(["sitter", "booking", booking.id], updated),
    onError: (failed) => setError(failed instanceof ApiError ? failed.message : "That didn't go through. Please try again."),
  });
  if (!asking) {
    return (
      <div>
        <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setAsking(true)}>
          This child is under 18 months
        </Button>
      </div>
    );
  }
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3">
      <p className="text-ink">
        Pacifyco doesn't take bookings for children under 18 months. You aren't required to care for them.
        Don't leave until an adult is with the child.
      </p>
      <Checkbox
        label="An adult is now with the child"
        checked={adultWithChild}
        onChange={(event) => setAdultWithChild(event.target.checked)}
      />
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button
          variant="secondary"
          loading={report.isPending}
          disabled={!adultWithChild}
          onClick={() => report.mutate()}
        >
          Tell Pacifyco
        </Button>
        <Button variant="tertiary" onClick={() => setAsking(false)}>
          Not now
        </Button>
      </div>
    </Card>
  );
}

/** She feels unsafe and needs to leave (6.5), only once the child is with a parent. */
function Unsafe({ booking }: { booking: SitterBookingDetail }) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [childWithParent, setChildWithParent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const report = useMutation({
    mutationFn: () =>
      apiFetch<SitterBookingDetail>(`/sitter/bookings/${booking.id}/unsafe`, {
        method: "POST",
        body: JSON.stringify({ child_with_parent: childWithParent }),
      }),
    onSuccess: (updated) => queryClient.setQueryData(["sitter", "booking", booking.id], updated),
    onError: (failed) => setError(failed instanceof ApiError ? failed.message : "That didn't go through. Please try again."),
  });
  if (!asking) {
    return (
      <div>
        <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setAsking(true)}>
          I feel unsafe
        </Button>
      </div>
    );
  }
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3">
      <p className="text-ink">
        Don't leave until the child is with a parent. Call Pacifyco on +91 8848873841, and 112 if you need help.
      </p>
      <Checkbox
        label="The child is now with a parent"
        checked={childWithParent}
        onChange={(event) => setChildWithParent(event.target.checked)}
      />
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button
          variant="secondary"
          loading={report.isPending}
          disabled={!childWithParent}
          onClick={() => report.mutate()}
        >
          Tell Pacifyco and leave
        </Button>
        <Button variant="tertiary" onClick={() => setAsking(false)}>
          Not now
        </Button>
      </div>
    </Card>
  );
}

/** What happens now that a report has been made about this booking. */
function ReportStatus({ booking, now }: { booking: SitterBookingDetail; now: Date }) {
  const report = booking.report!;
  const fee = rupees(SHOW_UP_FEE_PER_HOUR_PAISE * booking.hours);
  let text: string;
  if (report.kind === "only_man_home") {
    text =
      report.status === "open"
        ? "You've declined this booking, and we've told the family and Pacifyco. Make sure the children are with an adult, then you may leave."
        : report.status === "confirmed"
          ? `Pacifyco confirmed. You won't get a strike, and you'll be paid ${rupees(MAN_HOME_FEE_PAISE)}.`
          : "Pacifyco looked at your report and dismissed it.";
  } else if (report.kind === "sitter_no_show") {
    text =
      report.status === "open"
        ? "The family says you didn't arrive. Pacifyco will call you."
        : report.status === "confirmed"
          ? "Pacifyco confirmed you didn't arrive. It counts as a strike."
          : "Pacifyco looked at the family's report and dismissed it.";
  } else if (report.kind === "child_under_age") {
    const perHour = rupees(booking.pay_paise / booking.hours);
    text =
      report.status === "open"
        ? "We've told Pacifyco and the family. Don't leave until an adult is with the child."
        : report.status === "confirmed"
          ? `Pacifyco confirmed. You won't get a strike, and you'll be paid ${perHour} for that hour.`
          : "Pacifyco looked at your report and the booking goes ahead.";
  } else if (report.kind === "sitter_unsafe") {
    text =
      report.status === "open"
        ? "We've told Pacifyco and the family. Stay safe."
        : report.status === "confirmed"
          ? "Pacifyco confirmed. You won't get a strike, and you'll be paid for the time you worked."
          : "Pacifyco looked at your report and the booking goes ahead.";
  } else if (report.status === "confirmed") {
    text = `Pacifyco confirmed no one was home. You'll be paid a show-up fee of ${fee}.`;
  } else if (report.status === "dismissed") {
    text = "Pacifyco looked at your report and the booking goes ahead.";
  } else if (report.responded_at) {
    text = "The family has responded and is on the way. Please wait for them.";
  } else {
    const left = report.can_leave_at ? minutesLeft(report.can_leave_at, now) : null;
    text = left
      ? `We've told the family and Pacifyco. If no one responds in ${left}, you may leave.`
      : `No one has responded, so you may leave. Pacifyco will confirm your show-up fee of ${fee}.`;
  }
  return (
    <Card as="section" padding="roomy" role="status" className="border-l-4 border-coral">
      <p className="text-ink">{text}</p>
    </Card>
  );
}

const SITTER_CAN_CANCEL = ["pending_payment", "confirmed"];
const SITTER_NOTICE_MS = 8 * 60 * 60 * 1000; // 8 hours or more before the start: no penalty (6.5)

/** What cancelling now means for her (6.5). */
export function sitterCancelOutcome(booking: SitterBookingDetail, now: Date): string {
  if (new Date(booking.starts_at).getTime() - now.getTime() < SITTER_NOTICE_MS) {
    return (
      "It's less than 8 hours before the start, so this is a late cancellation: you'll get a strike and " +
      "won't be paid for this booking."
    );
  }
  return "It's 8 hours or more before the start, so there's no penalty. We'll tell the family and refund them.";
}

/** She can't make it after all. */
function CancelBooking({ booking }: { booking: SitterBookingDetail }) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cancel = useMutation({
    mutationFn: () => apiFetch<SitterBookingDetail>(`/sitter/bookings/${booking.id}/cancel`, { method: "POST" }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["sitter", "booking", booking.id], updated);
      void queryClient.invalidateQueries({ queryKey: ["sitter"] });
      showToast("Booking cancelled. We've told the family.");
    },
    onError: (failed) =>
      setError(failed instanceof ApiError ? failed.message : "We couldn't cancel it. Please try again."),
  });
  if (!asking) {
    return (
      <div>
        <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setAsking(true)}>
          I can't make this booking
        </Button>
      </div>
    );
  }
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3">
      <p className="text-ink">{sitterCancelOutcome(booking, new Date())}</p>
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" loading={cancel.isPending} onClick={() => cancel.mutate()}>
          Yes, cancel it
        </Button>
        <Button variant="tertiary" onClick={() => setAsking(false)}>
          Keep it
        </Button>
      </div>
    </Card>
  );
}

/** Her location, if she allows it; `null` for both if denied, unsupported or it times out (6.7). */
function currentLocation(): Promise<{ lat: number | null; lng: number | null }> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      resolve({ lat: null, lng: null });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => resolve({ lat: position.coords.latitude, lng: position.coords.longitude }),
      () => resolve({ lat: null, lng: null }),
      { timeout: 5000 },
    );
  });
}

function attemptsLeft(error: unknown): number | null {
  if (!(error instanceof ApiError) || error.code !== "wrong_code") return null;
  const details = error.details as { attempts_left?: unknown } | null;
  return typeof details?.attempts_left === "number" ? details.attempts_left : null;
}

/** Entering the family's check-in or check-out code (6.7): her location is recorded if she allows it. */
function CheckCodeForm({ booking, kind }: { booking: SitterBookingDetail; kind: "check-in" | "check-out" }) {
  const queryClient = useQueryClient();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = useMutation({
    mutationFn: async (value: string) => {
      const { lat, lng } = await currentLocation();
      return apiFetch<SitterBookingDetail>(`/sitter/bookings/${booking.id}/${kind}`, {
        method: "POST",
        body: JSON.stringify({ code: value, lat, lng }),
      });
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["sitter", "booking", booking.id], updated);
      void queryClient.invalidateQueries({ queryKey: ["sitter"] });
      setCode("");
      setError(null);
      showToast(kind === "check-in" ? "Checked in." : "Checked out.");
    },
    onError: (failed) => {
      const left = attemptsLeft(failed);
      setError(
        failed instanceof ApiError
          ? left !== null
            ? `${failed.message} ${left === 1 ? "1 try left." : `${left} tries left.`}`
            : failed.message
          : "That didn't go through. Please try again.",
      );
    },
  });
  if (booking.codes_locked) {
    return (
      <Card as="section" padding="roomy" role="alert">
        <p className="text-ink">Too many wrong codes were entered. Pacifyco has been told and will call you.</p>
      </Card>
    );
  }
  const noun = kind === "check-in" ? "Check-in" : "Check-out";
  const verb = kind === "check-in" ? "Check in" : "Check out";
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3">
      <p className="text-ink">Ask the family for the {noun.toLowerCase()} code and enter it here.</p>
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          if (!/^\d{4}$/.test(code)) {
            setError("Enter the 4-digit code.");
            return;
          }
          setError(null);
          submit.mutate(code);
        }}
        className="flex flex-col gap-3"
      >
        <TextInput
          label={`${noun} code`}
          value={code}
          onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 4))}
          inputMode="numeric"
          maxLength={4}
          error={error ?? undefined}
        />
        <div>
          <Button type="submit" loading={submit.isPending}>
            {verb}
          </Button>
        </div>
      </form>
    </Card>
  );
}

export function SitterBookingPage() {
  const { bookingId = "" } = useParams();
  const booking = useQuery({
    queryKey: ["sitter", "booking", bookingId],
    queryFn: () => apiFetch<SitterBookingDetail>(`/sitter/bookings/${bookingId}`),
    // While a report is open, check for the family's response (and the countdown) every 30 seconds.
    refetchInterval: (query) => (query.state.data?.report?.status === "open" ? 30_000 : false),
  });
  if (booking.isPending) return <p className="text-center text-muted">Loading…</p>;
  if (booking.isError) {
    return (
      <section className="mx-auto max-w-[40rem]">
        <EmptyState
          message="We couldn't find that booking."
          action={<ButtonLink to="/sitter/bookings">Your bookings</ButtonLink>}
        />
      </section>
    );
  }
  const data = booking.data;
  const contact = data.emergency_contact;
  const isRequest = data.status === "requested";
  return (
    <article className="mx-auto flex max-w-[40rem] flex-col gap-5">
      {isRequest ? (
        <BackLink to="/sitter/requests" label="Requests" />
      ) : (
        <BackLink to="/sitter/bookings" label="Your bookings" />
      )}
      <h1>{data.family_name}'s family</h1>
      <Card as="section" padding="roomy" className="flex flex-col gap-2">
        <p className="text-eyebrow text-muted uppercase">{sitterStatusText(data.status)}</p>
        <p className="text-h3">{formatBookingTime(new Date(data.starts_at), new Date(data.ends_at))}</p>
        <p className="text-ink">
          {sitterBookingLine(data)}
          {data.bath_time ? " Bath time included." : ""}
        </p>
        <p className="text-small text-muted">
          {rupees(data.pay_paise)} for {data.hours === 1 ? "1 hour" : `${data.hours} hours`}
        </p>
        {outingText(data) && <p className="text-ink">{outingText(data)}</p>}
      </Card>

      {isRequest && <Answer booking={data} />}

      {!data.address && data.pin_code && (
        <Card as="section" padding="roomy" className="flex flex-col gap-2">
          <h2 className="text-h3">Where</h2>
          <p className="text-ink">Near {data.pin_code}. The full address shows once the family has paid.</p>
        </Card>
      )}

      {data.address && (
        <Card as="section" padding="roomy" className="flex flex-col gap-2">
          <h2 className="text-h3">Where</h2>
          <p className="whitespace-pre-line text-ink">{data.address}</p>
          {data.pin_code && <p className="text-small text-muted">{data.pin_code}</p>}
        </Card>
      )}

      <Card as="section" padding="roomy" className="flex flex-col gap-4">
        <h2 className="text-h3">The children</h2>
        {data.children_details.map((child) => (
          <div key={child.name} className="flex flex-col gap-2 border-t border-line pt-4 first-of-type:border-t-0 first-of-type:pt-0">
            <p className="text-ui text-ink">
              {child.name}, {ageText(child.age_months)}
            </p>
            <dl className="flex flex-col gap-2">
              <Note label="Allergies" value={child.allergies} />
              <Note label="Medical notes and medicine" value={child.medical_notes} />
              <Note label="Routines" value={child.routines} />
            </dl>
          </div>
        ))}
        <p className="text-small text-muted">Only give medicine the family has written down here.</p>
      </Card>

      <Card as="section" padding="roomy" className="flex flex-col gap-2">
        <h2 className="text-h3">Cameras</h2>
        <p className="text-ink">
          {!data.cameras_on
            ? "The family says no cameras are on at home."
            : data.camera_locations
              ? `The family says cameras are on: ${data.camera_locations}`
              : "The family says cameras are on at home."}
        </p>
      </Card>

      {contact && (
        <Card as="section" padding="roomy" className="flex flex-col gap-2">
          <h2 className="text-h3">Emergency contact</h2>
          <p className="text-ink">
            {contact.name} ({contact.relationship})
          </p>
          <a href={`tel:${contact.phone}`} className="text-ui">
            {formatMobile(contact.phone)}
          </a>
          <p className="text-small text-muted">If you can't reach the family in an emergency.</p>
        </Card>
      )}
      {data.status === "confirmed" && todayInKolkata(new Date(data.starts_at)) === todayInKolkata() && (
        <CheckCodeForm booking={data} kind="check-in" />
      )}
      {data.status === "in_progress" && data.overtime?.status === "pending" && <OvertimeAnswer booking={data} />}
      {data.status === "in_progress" && <CheckCodeForm booking={data} kind="check-out" />}
      {["confirmed", "in_progress", "completed", "closed_by_admin"].includes(data.status) && (
        <div>
          <ButtonLink to={`/sitter/chats/${data.parent_id}`} variant="secondary" fullWidthOnPhone={false}>
            Message {data.family_name}
          </ButtonLink>
        </div>
      )}
      <ReviewCard<SitterBookingDetail>
        path={`/sitter/bookings/${data.id}/review`}
        queryKey={["sitter", "booking", data.id]}
        review={data.review}
        question={`How was the booking with ${data.family_name}?`}
        note="Only Pacifyco sees your rating and review. The family doesn't."
      />
      <BookingHelp
        role="sitter"
        bookingId={data.id}
        buttonsOpen={data.buttons_open}
        incident={data.incident}
        queryKey={["sitter", "booking", data.id]}
      />
      <ComplaintLink role="sitter" bookingId={data.id} />
      {data.report && <ReportStatus booking={data} now={new Date()} />}
      {!data.report &&
        ["confirmed", "in_progress"].includes(data.status) &&
        underWay(data.starts_at, data.ends_at, new Date()) && (
          <div className="flex flex-col gap-3">
            <NoOneHome booking={data} />
            <OnlyManHome booking={data} />
            <UnderAge booking={data} />
            <Unsafe booking={data} />
          </div>
        )}
      {SITTER_CAN_CANCEL.includes(data.status) && new Date(data.starts_at) > new Date() && (
        <CancelBooking booking={data} />
      )}
    </article>
  );
}
