import { Link, Navigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { AREA_PATH, useMe } from "../auth/useMe";
import { ButtonLink, Photo } from "../components/ui";
import { config } from "../config";

export function HomePage() {
  const { status } = useAuth();

  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>A little help for you. A little more fun for them.</h1>
      <p className="mt-4 text-body-lg text-muted">Pacify is getting ready for families in Bengaluru.</p>

      <div className="mx-auto mt-7 grid max-w-[40rem] grid-cols-2 gap-4 sm:gap-5">
        <Photo name="parentsDinnerCouple" aspect="4 / 5" sizes="(min-width: 640px) 20rem, 50vw" priority />
        <Photo
          name="sitterBlocks"
          aspect="4 / 5"
          sizes="(min-width: 640px) 20rem, 50vw"
          priority
          className="mt-7 [animation-delay:120ms]"
        />
      </div>

      <div className="mt-7">
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

// Signed-in people never linger on the marketing page: straight to joining, or straight to their area.
function SignedIn() {
  const me = useMe();

  if (me.isPending) return <p className="text-center text-muted">Loading your account…</p>;
  if (me.isError) return <p className="text-center text-muted">{me.error.message}</p>;

  const profile = me.data.profile;
  if (!profile) return <Navigate to="/join" replace />;
  return <Navigate to={AREA_PATH[profile.role]} replace />;
}
