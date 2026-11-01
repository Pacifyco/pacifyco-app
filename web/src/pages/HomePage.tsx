import { Link, Navigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { AREA_PATH, useMe } from "../auth/useMe";
import { ButtonLink } from "../components/ui";
import { config } from "../config";

export function HomePage() {
  const { status } = useAuth();

  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>A little help for you. A little more fun for them.</h1>
      <p className="mt-4 text-body-lg text-muted">Pacify is getting ready for families in Bengaluru.</p>

      <div className="mt-6">
        {status === "signed_in" && <SignedIn />}
        {status === "signed_out" && (
          <ButtonLink to="/sign-in" arrow>
            Sign in or join
          </ButtonLink>
        )}
      </div>

      {config.environment !== "production" && (
        <p className="mt-6 text-ui">
          <Link to="/dev/components">Components</Link>
        </p>
      )}
    </section>
  );
}

function SignedIn() {
  const { email } = useAuth();
  const me = useMe();

  if (me.isPending) return <p className="text-center text-muted">Loading your account…</p>;
  if (me.isError) return <p className="text-center text-muted">{me.error.message}</p>;

  const profile = me.data.profile;
  // Signed in for the first time: finish joining before anything else.
  if (!profile) return <Navigate to="/join" replace />;
  return (
    <div className="flex flex-col items-center gap-4">
      <p className="text-muted">You're signed in as {me.data.email ?? email}.</p>
      <ButtonLink to={AREA_PATH[profile.role]} arrow>
        Go to your account
      </ButtonLink>
    </div>
  );
}
