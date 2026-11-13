import { AREA_PATH } from "../auth/useMe";
import { BackLink, ButtonLink, Card } from "../components/ui";
import { SignOutButton } from "../layouts/AppLayout";
import { ThemeToggle } from "../theme/ThemeToggle";
import {
  ChecklistCard,
  PARENT_STEPS,
  SITTER_STEPS,
  useChecklist,
  type ParentChecklist as ParentChecklistData,
  type SitterChecklist as SitterChecklistData,
} from "./ProfileChecklist";

// "Your profile" (CLAUDE.md 6.13), opened from the profile button in the header: what's left to finish,
// each item linking to where it's done. Steps send people back here when they're saved.

function ParentProfile() {
  const checklist = useChecklist<ParentChecklistData>("parent");
  if (!checklist.isSuccess) return <p className="text-center text-muted">Loading your profile…</p>;
  const { items, finished } = checklist.data;
  const childrenVerified = items.find((item) => item.key === "children")?.status === "approved";
  // Parents can book before the birth certificates are checked; the booking waits (CLAUDE.md 6.4).
  const intro = !finished
    ? "Finish these to book a sitter."
    : childrenVerified
      ? "Your profile is finished."
      : "Your profile is finished, so you can book. A booking is confirmed once Pacifyco has checked your children's birth certificates.";
  return (
    <ChecklistCard
      heading={finished ? "Your profile" : "Finish your profile"}
      intro={intro}
      items={items}
      steps={PARENT_STEPS}
    />
  );
}

function SitterProfile() {
  const checklist = useChecklist<SitterChecklistData>("sitter");
  if (!checklist.isSuccess) return <p className="text-center text-muted">Loading your profile…</p>;
  const { items, live, application_rejected_reason: rejectedReason } = checklist.data;
  const allPassed = items.every((item) => item.status === "done" || item.status === "approved");
  const intro = rejectedReason
    ? `Pacifyco couldn't approve your application: ${rejectedReason}`
    : live
      ? "Your profile is live. Families can now find and book you."
      : allPassed
        ? "Every step has passed. Pacifyco will review your profile and let you know when it's live."
        : "Families can find you once every step passes and Pacifyco approves your profile.";
  return (
    <>
      <ChecklistCard
        heading={live ? "Your profile" : "Finish your profile"}
        intro={intro}
        items={items}
        steps={SITTER_STEPS}
        inOrder
      />
      {/* Sitters change their availability here once they're set up; their home is their bookings. */}
      <Card as="section" className="flex flex-col items-start gap-3">
        <h2 className="text-h3">Your availability</h2>
        <p className="text-small text-muted">Your usual week and days off. Families can book you inside these times.</p>
        <ButtonLink to="/sitter/availability" variant="secondary">
          Change your availability
        </ButtonLink>
      </Card>
    </>
  );
}

// On phones the header holds only the logo and the profile button, so the theme switch and Sign out
// live here (UX review 2026-11-13). On wider screens they stay in the header.
function Settings() {
  return (
    <Card as="section" className="flex flex-col gap-4 sm:hidden" aria-labelledby="settings-heading">
      <h2 id="settings-heading" className="text-h3">
        Settings
      </h2>
      <div className="flex items-center justify-between gap-3">
        <span className="text-ui text-ink">Theme</span>
        <ThemeToggle />
      </div>
      <div className="border-t border-line pt-2">
        <SignOutButton />
      </div>
    </Card>
  );
}

export function ProfilePage({ role }: { role: "parent" | "sitter" }) {
  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-4">
      <BackLink to={AREA_PATH[role]} label="Home" />
      {role === "parent" ? <ParentProfile /> : <SitterProfile />}
      <Settings />
    </section>
  );
}
