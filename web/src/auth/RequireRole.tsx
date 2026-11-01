import type { ReactNode } from "react";
import { Navigate } from "react-router";
import { useAuth } from "./AuthProvider";
import { AREA_PATH, useMe, type Role } from "./useMe";

const BLOCKED = new Set(["suspended", "removed"]);

// Wraps each role's area. The API enforces the same rules (app/auth.py); this only decides what to show.
export function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { status } = useAuth();
  const me = useMe();

  if (status === "signed_out") return <Navigate to="/sign-in" replace />;
  if (status === "loading" || me.isPending) return <p className="text-muted">Loading your account…</p>;
  if (me.isError) return <p className="text-muted">{me.error.message}</p>;

  const profile = me.data.profile;
  if (!profile) return <Navigate to="/join" replace />;
  if (BLOCKED.has(profile.status)) return <AccountOnHold removed={profile.status === "removed"} />;
  if (profile.role !== role) return <Navigate to={AREA_PATH[profile.role]} replace />;
  return <>{children}</>;
}

// CLAUDE.md 6.12: appeals within 15 days of the decision; contact details from CLAUDE.md 7.
export function AccountOnHold({ removed }: { removed: boolean }) {
  return (
    <section className="max-w-[62ch]">
      <h1>{removed ? "This account is closed." : "Your account is on hold."}</h1>
      <p className="mt-4 text-muted">
        {removed
          ? "The Pacify team has closed this account, so it can't be used any more."
          : "The Pacify team has paused this account, so it can't be used for now."}{" "}
        If you think this is a mistake, you can appeal within 15 days of the decision.
      </p>
      <p className="mt-4 text-muted">
        Contact us at <a href="mailto:query.pacifyco@gmail.com">query.pacifyco@gmail.com</a> or{" "}
        <a href="tel:+918848873841">+91 8848873841</a>.
      </p>
    </section>
  );
}
