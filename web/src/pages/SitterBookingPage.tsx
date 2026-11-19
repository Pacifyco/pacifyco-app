import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";
import { BackLink, Button, ButtonLink, Card, EmptyState, showToast } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { formatBookingTime, formatMobile } from "../lib/format";
import { rupees } from "../lib/prices";
import { sitterBookingLine, sitterStatusText, type SitterBookingItem } from "./SitterBookingsPage";
import { answerByText } from "./SitterRequestsPage";

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

export function SitterBookingPage() {
  const { bookingId = "" } = useParams();
  const booking = useQuery({
    queryKey: ["sitter", "booking", bookingId],
    queryFn: () => apiFetch<SitterBookingDetail>(`/sitter/bookings/${bookingId}`),
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
    </article>
  );
}
