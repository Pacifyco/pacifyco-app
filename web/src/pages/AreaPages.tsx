import { ButtonLink, Photo } from "../components/ui";
import { formatDate } from "../lib/format";
import { CONSENT_VERSION, useConsent } from "./ConsentPage";

// Placeholders for each role's area (gated by RequireRole in routes.tsx).

export function ParentHomePage() {
  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>Time for you.</h1>
      <p className="mt-4 text-muted">Your bookings, hours and sitters will be here.</p>
      <Photo name="parentsDinnerFriends" priority className="mt-6" />
      <ConsentPrompt />
    </section>
  );
}

// Until the current consent form is accepted, ask for it; children's documents need it (CLAUDE.md 7).
function ConsentPrompt() {
  const consent = useConsent();
  if (!consent.isSuccess) return null;
  const { version, accepted_at: acceptedAt } = consent.data;
  if (acceptedAt && version === CONSENT_VERSION) {
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
  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>Your work with Pacify.</h1>
      <p className="mt-4 text-muted">Your bookings, availability and earnings will be here.</p>
      <Photo name="sitterSlide" priority className="mt-6" />
    </section>
  );
}

export function AdminHomePage() {
  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>Admin</h1>
      <p className="mt-4 text-muted">Verifications, payments, payouts and incidents will be here.</p>
    </section>
  );
}
