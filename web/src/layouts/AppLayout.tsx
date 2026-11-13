import { Link, Outlet, useLocation } from "react-router";
import { SIGN_IN_PATH } from "../pages/SignInPage";
import wordmarkReversedUrl from "../assets/brand/wordmark-reversed.png";
import wordmarkUrl from "../assets/brand/wordmark.png";
import { useAuth } from "../auth/AuthProvider";
import { useMe } from "../auth/useMe";
import { Toaster } from "../components/ui";
import { cx } from "../components/ui/cx";
import { ThemeToggle } from "../theme/ThemeToggle";
import { ProfileButton } from "./ProfileButton";

export function AppLayout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-line bg-surface-raised">
        <div className="mx-auto flex max-w-content items-center justify-between gap-3 px-4 py-2 sm:px-5 sm:py-3">
          {/* Wordmark: 24px tall on phones, 28px on desktop; reversed version in dark mode (design.md
              section 6). PNG copies of the supplied files (sources in /assets); swap for SVGs when supplied. */}
          <Link to="/" aria-label="Pacify home" className="inline-flex shrink-0 py-1 no-underline">
            <img src={wordmarkUrl} alt="" width={426} height={112} className="h-6 w-auto sm:h-7 dark:hidden" />
            <img
              src={wordmarkReversedUrl}
              alt=""
              width={426}
              height={112}
              className="hidden h-6 w-auto sm:h-7 dark:block"
            />
          </Link>
          <HeaderActions />
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-content flex-1 px-4 py-5 sm:px-5 sm:py-7">
        <Outlet />
      </main>

      <footer className="border-t border-line px-4 py-4 sm:px-5">
        <nav aria-label="Legal" className="mx-auto flex max-w-content flex-wrap justify-center gap-5 text-small">
          {/* Only the privacy policy (Reuben, 2026-11-13). The terms are linked where people agree to them:
              the consent pages. */}
          <Link to="/privacy">Privacy policy</Link>
        </nav>
      </footer>
      <Toaster />
    </div>
  );
}

// On phones, parents and sitters find Sign out and the theme switch on "Your profile" instead, so the
// header holds just the logo and the profile button (UX review 2026-11-13). Admins have no profile page.
function HeaderActions() {
  const me = useMe();
  const role = me.data?.profile?.role;
  const hasProfilePage = role === "parent" || role === "sitter";
  return (
    <div className="flex items-center gap-2 sm:gap-3">
      <div className={cx("items-center gap-2 sm:gap-3", hasProfilePage ? "hidden sm:flex" : "flex")}>
        <AccountLink />
        <ThemeToggle />
      </div>
      <ProfileButton />
    </div>
  );
}

export function SignOutButton() {
  const { signOut } = useAuth();
  return (
    <button
      type="button"
      onClick={signOut}
      className="min-h-[44px] whitespace-nowrap text-ui text-coral-deep underline-offset-4 hover:underline"
    >
      Sign out
    </button>
  );
}

function AccountLink() {
  const { status, available } = useAuth();
  const { pathname, search } = useLocation();
  if (status === "signed_in") return <SignOutButton />;
  // No "Sign in" link while the sign-in box is already open.
  if (status === "signed_out" && available && !(pathname === "/" && new URLSearchParams(search).has("signin"))) {
    return (
      <Link to={SIGN_IN_PATH} className="text-ui">
        Sign in
      </Link>
    );
  }
  return null;
}
