import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, CreditCard, Siren, Wallet } from "lucide-react";
import { ButtonLink, Card, EmptyState, IconTile } from "../components/ui";
import { apiFetch } from "../lib/api";

// Each role's home (gated by RequireRole in routes.tsx). Parents have none: they land on Find a sitter.
// Sitters land on their bookings; a sitter who hasn't set her availability yet is asked to do that first.
// After that she changes it from "Your profile".

type Availability = { week: unknown[]; days_off: string[] };

export function SitterHomePage() {
  // Same query key as the availability page, so saving there updates this page.
  const availability = useQuery({
    queryKey: ["sitter-availability"],
    queryFn: () => apiFetch<Availability>("/sitter/availability"),
  });
  const firstTime = availability.isSuccess && availability.data.week.length === 0;

  return (
    <section className="mx-auto flex max-w-[40rem] flex-col gap-4">
      <h1 className="text-h3">Your bookings</h1>
      {firstTime && (
        <Card as="section" className="flex flex-col items-start gap-3">
          <h2 className="text-h3">Set your availability</h2>
          <p className="text-small text-muted">
            Tell us your usual week, so families can book you inside those times.
          </p>
          <ButtonLink to="/sitter/availability" arrow>
            Your availability
          </ButtonLink>
        </Card>
      )}
      {availability.isPending ? (
        <p className="text-muted">Loading…</p>
      ) : (
        <EmptyState message="No bookings yet. Confirmed bookings will show here." />
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
