import { BadgeCheck, Calendar, Clock, CreditCard, HeartHandshake, Siren, Wallet } from "lucide-react";
import { useMe } from "../auth/useMe";
import { ButtonLink, IconTile } from "../components/ui";
import {
  ChecklistCard,
  PARENT_STEPS,
  SITTER_STEPS,
  useChecklist,
  type ParentChecklist as ParentChecklistData,
  type SitterChecklist as SitterChecklistData,
} from "./ProfileChecklist";

// Each role's home (gated by RequireRole in routes.tsx). Parents and sitters land here straight after
// sign-up and see their "finish your profile" checklist (CLAUDE.md 6.13). Headings stay exactly as
// signIn.test.tsx expects them.

function firstName(fullName: string | null | undefined): string | undefined {
  return fullName?.trim().split(/\s+/)[0];
}

function ParentChecklist() {
  const checklist = useChecklist<ParentChecklistData>("parent");
  if (!checklist.isSuccess) return null;
  const { items, finished } = checklist.data;
  const childrenVerified = items.find((item) => item.key === "children")?.status === "approved";
  // Parents can book before the birth certificates are checked; the booking waits (CLAUDE.md 6.4).
  const intro = !finished
    ? "Finish these to book a sitter."
    : childrenVerified
      ? "Your profile is finished."
      : "Your profile is finished, so you can book. A booking is confirmed once Pacify has checked your children's birth certificates.";
  return (
    <div className="mt-7">
      <ChecklistCard
        heading={finished ? "Your profile" : "Finish your profile"}
        intro={intro}
        items={items}
        steps={PARENT_STEPS}
      />
    </div>
  );
}

export function ParentHomePage() {
  const me = useMe();
  const name = firstName(me.data?.profile?.full_name);

  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>Time for you.</h1>
      <p className="mt-4 text-muted">
        {name ? `Hello ${name}, ` : ""}your bookings and sitters will be here.
      </p>
      <ParentChecklist />
      <div className="mt-7 grid gap-5 sm:grid-cols-3">
        <IconTile icon={HeartHandshake} label="Start with a short booking" />
        <IconTile icon={Calendar} label="Scheduled care" />
        <IconTile icon={Wallet} label="Pay by the hour" />
      </div>
    </section>
  );
}

function SitterChecklist() {
  const checklist = useChecklist<SitterChecklistData>("sitter");
  if (!checklist.isSuccess) return null;
  const { items, live } = checklist.data;
  const allPassed = items.every((item) => item.status === "done" || item.status === "approved");
  const intro = live
    ? "Your profile is live. Families can now find and book you."
    : allPassed
      ? "Every step has passed. Pacify will review your profile and let you know when it's live."
      : "Families can find you once every step passes and Pacify approves your profile.";
  return (
    <div className="mt-7">
      <ChecklistCard
        heading={live ? "Your profile" : "Finish your profile"}
        intro={intro}
        items={items}
        steps={SITTER_STEPS}
      />
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
      <SitterChecklist />
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
      <div className="mt-7 flex justify-center">
        <ButtonLink to="/admin/verifications" arrow>
          Open the verification queue
        </ButtonLink>
      </div>
      <div className="mt-7 grid gap-5 sm:grid-cols-2">
        <IconTile icon={BadgeCheck} label="Verifications" />
        <IconTile icon={CreditCard} label="Payments" />
        <IconTile icon={Wallet} label="Payouts" />
        <IconTile icon={Siren} label="Incidents" />
      </div>
    </section>
  );
}
