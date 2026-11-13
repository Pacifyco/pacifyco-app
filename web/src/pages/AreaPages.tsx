import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, CalendarClock, CircleCheck, CreditCard, Siren, Wallet, X } from "lucide-react";
import { useState } from "react";
import { useMe } from "../auth/useMe";
import { Link } from "react-router";
import { ButtonLink, Card, EmptyState, IconTile } from "../components/ui";
import { apiFetch } from "../lib/api";
import { useChecklist, type SitterChecklist } from "./ProfileChecklist";

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
        {waiting ? `, ${waiting} with Pacify for review` : ""}.{" "}
        {toDo
          ? "Families can find you once every step passes and Pacify approves your profile."
          : "Pacify is checking what you've sent. We'll let you know as soon as your profile is live."}
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
        Families {pinCode ? `near ${pinCode}` : "near you"} can now find you on Pacify.
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
          <h2 className="mt-2 text-ui font-semibold">Your bookings</h2>
          <EmptyState message="No bookings yet. Confirmed bookings will show here." />
          <FirstBooking hasWeek={hasWeek} />
        </>
      )}
    </section>
  );
}

export function AdminHomePage() {
  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>Admin</h1>
      <p className="mt-3 text-muted">Verifications, payments, payouts and incidents will be here.</p>
      <div className="mt-5 flex justify-center">
        <ButtonLink to="/admin/verifications" arrow>
          Open the verification queue
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
