import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { BackLink, Button, ButtonLink, Card, Checkbox, EmptyState, showToast } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { formatBookingTime, formatMobile } from "../lib/format";
import { rupees } from "../lib/prices";
import { sitterBookingLine, sitterStatusText, type SitterBookingItem } from "./SitterBookingsPage";
import { answerByText } from "./SitterRequestsPage";
import { MAN_HOME_FEE_PAISE, SHOW_UP_FEE_PER_HOUR_PAISE, minutesLeft, underWay, type BookingReport } from "../lib/reports";

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
      {data.report && <ReportStatus booking={data} now={new Date()} />}
      {!data.report &&
        ["confirmed", "in_progress"].includes(data.status) &&
        underWay(data.starts_at, data.ends_at, new Date()) && (
          <div className="flex flex-col gap-3">
            <NoOneHome booking={data} />
            <OnlyManHome booking={data} />
          </div>
        )}
      {SITTER_CAN_CANCEL.includes(data.status) && new Date(data.starts_at) > new Date() && (
        <CancelBooking booking={data} />
      )}
    </article>
  );
}
