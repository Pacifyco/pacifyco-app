import { BadgeCheck, Calendar, Clock, CreditCard, HeartHandshake, Siren, Wallet } from "lucide-react";
import { useMe } from "../auth/useMe";
import { ButtonLink, IconTile } from "../components/ui";
import { formatDate } from "../lib/format";
import { CONSENT_VERSION, useConsent } from "./ConsentPage";

// Placeholders for each role's area (gated by RequireRole in routes.tsx). Headings stay exactly as
// signIn.test.tsx expects them; everything below personalises the page and previews what's coming.

function firstName(fullName: string | undefined): string | undefined {
  return fullName?.trim().split(/\s+/)[0];
}

// Sunken-panel pattern already used by ConsentPrompt and JoinPage's confirmation step.
function PendingNote({ children }: { children: string }) {
  return (
    <p className="mx-auto mt-6 max-w-[50ch] rounded-lg bg-surface-sunken p-5 text-small text-ink">{children}</p>
  );
}

export function ParentHomePage() {
  const me = useMe();
  const name = firstName(me.data?.profile?.full_name);

  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>Time for you.</h1>
      <p className="mt-4 text-muted">
        {name ? `Hello ${name}, ` : ""}your bookings, hours and sitters will be here.
      </p>
      {me.data?.profile?.status === "pending" && (
        <PendingNote>Your account is being verified. We'll be in touch once that's done.</PendingNote>
      )}
      <div className="mt-7 grid gap-5 sm:grid-cols-3">
        <IconTile icon={HeartHandshake} label="Meet a sitter first" />
        <IconTile icon={Calendar} label="Scheduled care" />
        <IconTile icon={Wallet} label="Hour packs" />
      </div>
      <ConsentPrompt />
    </section>
  );
}

// Until the current consent form is accepted, ask for it; children's documents need it (CLAUDE.md 7).
function ConsentPrompt() {
  const consent = useConsent();
  if (!consent.isSuccess) return null;
  const { version, required_accepted: requiredAccepted, accepted_at: acceptedAt } = consent.data;
  if (requiredAccepted && acceptedAt && version === CONSENT_VERSION) {
    return <p className="mt-6 text-small text-muted">Parental consent given on {formatDate(new Date(acceptedAt))}.</p>;
  }
  return (
    <div className="mt-6 flex flex-col items-center gap-4 rounded-lg bg-surface-sunken p-5">
      <p className="text-ink">Before you add your children, please read and accept the parental consent form.</p>
      <ButtonLink to="/parent/consent" arrow>
        Read the consent form
      </ButtonLink>
    </div>
  );
}

export function SitterHomePage() {
  const me = useMe();
  const name = firstName(me.data?.profile?.full_name);

  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>Your work with Pacify.</h1>
      <p className="mt-4 text-muted">
        {name ? `Hello ${name}. ` : ""}Your bookings, availability and earnings will be here.
      </p>
      {me.data?.profile?.status === "pending" && (
        <PendingNote>Your profile is being verified. We'll let you know once it's ready to go live.</PendingNote>
      )}
      <div className="mt-7 grid gap-5 sm:grid-cols-3">
        <IconTile icon={Calendar} label="Booking requests" />
        <IconTile icon={Clock} label="Your availability" />
        <IconTile icon={Wallet} label="Your earnings" />
      </div>
    </section>
  );
}

export function AdminHomePage() {
  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>Admin</h1>
      <p className="mt-4 text-muted">Verifications, payments, payouts and incidents will be here.</p>
      <div className="mt-7 grid gap-5 sm:grid-cols-2">
        <IconTile icon={BadgeCheck} label="Verifications" />
        <IconTile icon={CreditCard} label="Payments" />
        <IconTile icon={Wallet} label="Payouts" />
        <IconTile icon={Siren} label="Incidents" />
      </div>
    </section>
  );
}
