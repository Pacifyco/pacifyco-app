import { Navigate, useSearchParams } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { AREA_PATH, useMe } from "../auth/useMe";
import { Button, LoadingScreen, Photo } from "../components/ui";
import { SignInBox } from "./SignInPage";

// Signed-in people never see this marketing page: a loading buffer covers the moment while we
// decide whether to send them to /join or straight to their area, so nothing flashes underneath it.
// Signing in happens here too: "Sign in or join" opens the sign-in box in place of the button (Reuben,
// 2026-11-13; there's no separate sign-in page). The box is open whenever the address has ?signin, so
// "Sign in" links elsewhere (SIGN_IN_PATH) and Back work.
export function HomePage() {
  const { status } = useAuth();
  const [params, setParams] = useSearchParams();
  const signingIn = params.has("signin");

  if (status === "loading") return <LoadingScreen />;
  if (status === "signed_in") return <SignedIn />;

  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>A little help for you. A little more fun for them.</h1>
      <p className="mt-4 text-body-lg text-muted">Pacify is getting ready for families in Bengaluru.</p>

      {/* "Sign in or join" sits in the first screen, above the photos (UX review 2026-11-13). Once
          pressed, the sign-in box opens below the photos (Reuben, 2026-11-13). */}
      {!signingIn && (
        <div className="mt-6">
          <Button arrow fullWidthOnPhone={false} onClick={() => setParams({ signin: "" })}>
            Sign in or join
          </Button>
        </div>
      )}

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

      {signingIn && (
        <div className="mt-7">
          <SignInBox autoFocus />
        </div>
      )}
    </section>
  );
}

function SignedIn() {
  const me = useMe();

  if (me.isPending) return <LoadingScreen />;
  if (me.isError) return <p className="text-center text-muted">{me.error.message}</p>;

  const profile = me.data.profile;
  if (!profile) return <Navigate to="/join" replace />;
  return <Navigate to={AREA_PATH[profile.role]} replace />;
}
