import type { ReactNode } from "react";
import { BadgeCheck, Calendar, Clock, CreditCard, HeartHandshake, Siren, Wallet } from "lucide-react";
import { useMe } from "../auth/useMe";
import { ButtonLink, IconTile } from "../components/ui";

// Each role's home (gated by RequireRole in routes.tsx). Parents and sitters land here straight after
// sign-up; what's left of their profile is in "Your profile", reached from the header's profile button and
// its "finish your profile" bubble (CLAUDE.md 6.13). Kept short so it fits a phone screen without scrolling.

function firstName(fullName: string | null | undefined): string | undefined {
  return fullName?.trim().split(/\s+/)[0];
}

// Extra room at the top on phones, so the profile button's bubble doesn't cover the heading.
const HOME = "mx-auto max-w-[62ch] pt-6 text-center sm:pt-0";

function Tiles({ children }: { children: ReactNode }) {
  return <div className="mt-6 grid grid-cols-3 gap-3 sm:gap-5">{children}</div>;
}

export function ParentHomePage() {
  const me = useMe();
  const name = firstName(me.data?.profile?.full_name);

  return (
    <section className={HOME}>
      <h1>Time for you.</h1>
      <p className="mt-3 text-muted">
        {name ? `Hello ${name}, your` : "Your"} bookings and sitters will be here.
      </p>
      <div className="mt-5 flex justify-center">
        <ButtonLink to="/parent/sitters" arrow>
          Find a sitter
        </ButtonLink>
      </div>
      <Tiles>
        <IconTile icon={HeartHandshake} label="Start with a short booking" />
        <IconTile icon={Calendar} label="Scheduled care" />
        <IconTile icon={Wallet} label="Pay by the hour" />
      </Tiles>
    </section>
  );
}

export function SitterHomePage() {
  const me = useMe();
  const name = firstName(me.data?.profile?.full_name);

  return (
    <section className={HOME}>
      <h1>Your work with Pacify.</h1>
      <p className="mt-3 text-muted">
        {name ? `Hello ${name}. ` : ""}Your bookings, availability and earnings will be here.
      </p>
      <div className="mt-5 flex justify-center">
        <ButtonLink to="/sitter/availability" arrow>
          Your availability
        </ButtonLink>
      </div>
      <Tiles>
        <IconTile icon={Calendar} label="Booking requests" />
        <IconTile icon={Clock} label="Your availability" />
        <IconTile icon={Wallet} label="Your earnings" />
      </Tiles>
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
