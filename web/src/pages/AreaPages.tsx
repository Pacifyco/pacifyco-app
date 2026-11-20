import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, CalendarClock, CircleCheck, CreditCard, Siren, Wallet, X } from "lucide-react";
import { useState } from "react";
import { useMe } from "../auth/useMe";
import { Link } from "react-router";
import { ButtonLink, Card, EmptyState, IconTile } from "../components/ui";
import { formatBookingTime, formatDay, formatTime } from "../lib/format";
import { apiFetch } from "../lib/api";
import { useChecklist, type SitterChecklist } from "./ProfileChecklist";
import { STRIKES_KEY, type SitterStrikes } from "./SitterStrikesPage";
import { sitterBookingLine, type SitterBookingItem, type SitterBookingList } from "./SitterBookingsPage";

// Each role's home (gated by RequireRole in routes.tsx). Parents have none: they land on Find a sitter.
// The sitter's home (UX review 2026-11-13): a greeting; while she isn't live, where her application
// stands; once she's approved, a one-time welcome and what gets her a first booking; then her bookings.

type Availability = { week: unknown[]; days_off: string[] };

const WELCOMED_KEY = "pacify.sitter-approved-seen";

function seenWelcome(): boolean {
  try {
    return localStorage.getItem(WELCOMED_KEY) === "1";
  } catch {
    return false;
  }
}

function ApplicationProgress({ checklist }: { checklist: SitterChecklist }) {
  const done = checklist.items.filter((item) => item.status === "done" || item.status === "approved").length;
  const waiting = checklist.items.filter((item) => item.status === "waiting").length;
  const toDo = checklist.items.length - done - waiting;
  return (
    <Card as="section" className="flex flex-col items-start gap-3 border-l-4 border-coral">
      <h2 className="text-h3">{toDo ? "Finish your application" : "Your application is in review"}</h2>
      <p className="text-small text-muted">
        {done} of {checklist.items.length} steps done
        {waiting ? `, ${waiting} with Pacifyco for review` : ""}.{" "}
        {toDo
          ? "Families can find you once every step passes and Pacifyco approves your profile."
          : "Pacifyco is checking what you've sent. We'll let you know as soon as your profile is live."}
      </p>
      <ButtonLink to="/sitter/profile" arrow={toDo > 0} variant={toDo ? "primary" : "secondary"}>
        {toDo ? "Continue your application" : "See your steps"}
      </ButtonLink>
    </Card>
  );
}

function ApprovedWelcome({ pinCode, onClose }: { pinCode: string | null; onClose: () => void }) {
  return (
    <Card as="section" className="relative flex flex-col items-start gap-2 border-l-4 border-trust">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute top-3 right-3 flex size-[44px] items-center justify-center rounded-pill text-muted hover:bg-surface-sunken"
      >
        <X aria-hidden="true" size={20} strokeWidth={1.75} />
      </button>
      <p className="flex items-center gap-2 text-ui text-trust">
        <CircleCheck aria-hidden="true" size={20} strokeWidth={1.75} />
        You're approved
      </p>
      <p className="pr-7 text-ink">
        Families {pinCode ? `near ${pinCode}` : "near you"} can now find you on Pacifyco.
      </p>
    </Card>
  );
}

function FirstBooking({ hasWeek }: { hasWeek: boolean }) {
  return (
    <Card as="section" className="flex flex-col gap-4">
      <h2 className="text-h3">Get your first booking</h2>
      <ol className="flex flex-col gap-3 text-small">
        <li className="flex items-start gap-3">
          {hasWeek ? (
            <CircleCheck aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-trust" />
          ) : (
            <CalendarClock aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-coral-deep" />
          )}
          <span>
            {hasWeek ? "Your usual week is set. " : "Set your usual week, so families can book you inside it. "}
            <Link to="/sitter/availability">{hasWeek ? "Change it" : "Set your availability"}</Link>
          </span>
        </li>
        <li className="flex items-start gap-3">
          <CalendarClock aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-coral-deep" />
          <span>
            Families new to you are asked to start with a 1-hour booking while they're at home. Confirmed bookings show
            here.
          </span>
        </li>
      </ol>
    </Card>
  );
}

/** Strikes that count (6.6): whether she's blocked from new bookings, and where to see them. */
function StrikesNotice() {
  const strikes = useQuery({ queryKey: STRIKES_KEY, queryFn: () => apiFetch<SitterStrikes>("/sitter/strikes") });
  if (!strikes.data || strikes.data.counting === 0) return null;
  const until = strikes.data.blocked_until ? new Date(strikes.data.blocked_until) : null;
  return (
    <Card as="section" className="flex flex-col items-start gap-3 border-l-4 border-coral">
      <p className="text-ui text-ink">
        {until
          ? `You can't take new bookings until ${formatDay(until)}, ${formatTime(until)}.`
          : `You have ${strikes.data.counting === 1 ? "a strike" : `${strikes.data.counting} strikes`} from the last 6 months.`}
      </p>
      <Link to="/sitter/strikes">See your strikes</Link>
    </Card>
  );
}

/** Requests waiting for her answer: they lapse unanswered, so they come first (6.4). */
function RequestsWaiting() {
  const list = useQuery({ queryKey: ["sitter", "requests"], queryFn: () => apiFetch<SitterBookingItem[]>("/sitter/requests") });
  const count = list.data?.length ?? 0;
  if (!count) return null;
  return (
    <Card as="section" className="flex flex-col items-start gap-3 border-l-4 border-coral">
      <p className="text-ui text-ink">
        {count === 1 ? "A family would like to book you." : `${count} families would like to book you.`} Please answer
        before the request lapses.
      </p>
      <ButtonLink to="/sitter/requests" arrow>
        {count === 1 ? "See the request" : "See the requests"}
      </ButtonLink>
    </Card>
  );
}

/** Her next booking, and the way to all of them. */
function NextBooking() {
  const list = useQuery({ queryKey: ["sitter", "bookings"], queryFn: () => apiFetch<SitterBookingList>("/sitter/bookings") });
  if (list.isPending) return <p className="text-muted">Loading…</p>;
  const next = list.data?.upcoming[0];
  if (!next) {
    return (
      <EmptyState
        message="No bookings yet. Confirmed bookings will show here."
        action={list.data?.past.length ? <Link to="/sitter/bookings?show=past">See past bookings</Link> : undefined}
      />
    );
  }
  const more = (list.data?.upcoming.length ?? 1) - 1;
  return (
    <div className="flex flex-col gap-2">
      <Link to={`/sitter/bookings/${next.id}`} className="text-ink no-underline">
        <Card as="article" className="flex flex-col gap-2">
          <p className="text-eyebrow text-muted uppercase">Next booking</p>
          <p className="text-h3">{formatBookingTime(new Date(next.starts_at), new Date(next.ends_at))}</p>
          <p className="text-body text-ink">{sitterBookingLine(next)}</p>
        </Card>
      </Link>
      <Link to="/sitter/bookings" className="text-small">
        {more > 0 ? `See all your bookings (${more} more coming up)` : "See all your bookings"}
      </Link>
    </div>
  );
}

export function SitterHomePage() {
  const me = useMe();
  const checklist = useChecklist<SitterChecklist>("sitter");
  // Same query key as the availability page, so saving there updates this page.
  const availability = useQuery({
    queryKey: ["sitter-availability"],
    queryFn: () => apiFetch<Availability>("/sitter/availability"),
  });
  const [welcomed, setWelcomed] = useState(seenWelcome);
  const firstName = me.data?.profile?.full_name?.trim().split(/\s+/)[0];
  const live = checklist.isSuccess && checklist.data.live;
  const hasWeek = availability.isSuccess && availability.data.week.length > 0;

  function closeWelcome() {
    setWelcomed(true);
    try {
      localStorage.setItem(WELCOMED_KEY, "1");
    } catch {
      // Private browsing: it shows again next time, which is fine.
    }
  }

  return (
    <section className="mx-auto flex max-w-[40rem] flex-col gap-4">
      <h1 className="text-h3">{firstName ? `Hi ${firstName}.` : "Hello."}</h1>
      {checklist.isPending || availability.isPending ? (
        <p className="text-muted">Loading…</p>
      ) : !live && checklist.isSuccess ? (
        <ApplicationProgress checklist={checklist.data} />
      ) : (
        <>
          {!welcomed && <ApprovedWelcome pinCode={me.data?.profile?.pin_code ?? null} onClose={closeWelcome} />}
          <StrikesNotice />
          <RequestsWaiting />
          <h2 className="mt-2 text-ui font-semibold">Your bookings</h2>
          <NextBooking />
          <FirstBooking hasWeek={hasWeek} />
        </>
      )}
    </section>
  );
}

/** A count of bookings needing a call (overdue check-outs, locked codes), if there are any (6.7). */
function OverdueBanner() {
  const needsAttention = useQuery({
    queryKey: ["admin", "overdue-checkouts"],
    queryFn: () => apiFetch<unknown[]>("/admin/overdue-checkouts"),
    refetchInterval: 30_000,
  });
  const count = needsAttention.data?.length ?? 0;
  if (!needsAttention.isSuccess || count === 0) return null;
  return (
    <Card
      as="section"
      padding="roomy"
      role="alert"
      className="mt-5 flex flex-col items-start gap-3 border-l-4 border-coral text-left"
    >
      <p className="text-ink">
        {count === 1 ? "1 booking needs" : `${count} bookings need`} a call: an overdue check-out, or
        codes locked.
      </p>
      <ButtonLink to="/admin/overdue-checkouts" variant="secondary">
        Open overdue check-outs
      </ButtonLink>
    </Card>
  );
}

export function AdminHomePage() {
  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>Admin</h1>
      <p className="mt-3 text-muted">Verifications, payments, payouts and incidents will be here.</p>
      <OverdueBanner />
      <div className="mt-5 flex flex-wrap justify-center gap-3">
        <ButtonLink to="/admin/verifications" arrow>
          Open the verification queue
        </ButtonLink>
        <ButtonLink to="/admin/payments" variant="secondary">
          Check payments
        </ButtonLink>
        <ButtonLink to="/admin/reports" variant="secondary">
          Reports
        </ButtonLink>
        <ButtonLink to="/admin/overdue-checkouts" variant="secondary">
          Overdue check-outs
        </ButtonLink>
      </div>
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4 sm:gap-5">
        <IconTile icon={BadgeCheck} label="Verifications" />
        <IconTile icon={CreditCard} label="Payments" />
        <IconTile icon={Wallet} label="Payouts" />
        <IconTile icon={Siren} label="Incidents" />
      </div>
    </section>
  );
}
