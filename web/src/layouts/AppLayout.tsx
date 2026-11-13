import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, Outlet, useLocation } from "react-router";
import { SIGN_IN_PATH } from "../pages/SignInPage";
import wordmarkReversedUrl from "../assets/brand/wordmark-reversed.png";
import wordmarkUrl from "../assets/brand/wordmark.png";
import { useAuth } from "../auth/AuthProvider";
import { useMe } from "../auth/useMe";
import { Toaster } from "../components/ui";
import { cx } from "../components/ui/cx";
import { ThemeToggle } from "../theme/ThemeToggle";
import { HeaderBackContext, type BackTarget } from "./headerBack";
import { ProfileButton } from "./ProfileButton";

const PINNED_AFTER = 64; // px scrolled before the header's own Back link shows
const MOVE = 8; // px of scroll in one direction before the header hides or comes back

/** Where the page is scrolled: `scrolled` once past the top, `hidden` while scrolling down. */
function useHeaderScroll() {
  const [state, setState] = useState({ scrolled: false, hidden: false });
  useEffect(() => {
    let last = window.scrollY;
    function onScroll() {
      const y = Math.max(window.scrollY, 0);
      if (Math.abs(y - last) < MOVE) return;
      setState({ scrolled: y > PINNED_AFTER, hidden: y > last && y > PINNED_AFTER });
      last = y;
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return state;
}

function HeaderBack({ target }: { target: BackTarget }) {
  const content = (
    <>
      <ArrowLeft aria-hidden="true" size={18} strokeWidth={1.75} />
      <span className="max-w-[9rem] truncate">{target.label}</span>
    </>
  );
  const className = "inline-flex min-h-[44px] shrink-0 items-center gap-1 text-small text-coral-deep no-underline";
  return target.to ? (
    <Link to={target.to} className={className}>
      {content}
    </Link>
  ) : (
    <button type="button" onClick={target.onBack} className={className}>
      {content}
    </button>
  );
}

// The header stays pinned to the top: it slides away while you scroll down and comes back as soon as you
// scroll up, with the page's Back link once you're past the top (Reuben, 2026-11-13: on an iPhone in the
// Google app, the app's search bar covered the logo and Back after scrolling).
export function AppLayout() {
  const [back, setBack] = useState<BackTarget | null>(null);
  const { scrolled, hidden } = useHeaderScroll();

  return (
    <HeaderBackContext.Provider value={setBack}>
    <div className="flex min-h-dvh flex-col">
      <header
        className={cx(
          "sticky top-0 z-30 border-b border-line bg-surface-raised transition-transform duration-200 ease-calm motion-reduce:transition-none",
          hidden && "-translate-y-full",
        )}
      >
        <div className="mx-auto flex max-w-content items-center justify-between gap-3 px-4 py-2 sm:px-5 sm:py-3">
          {scrolled && back && <HeaderBack target={back} />}
          {/* Wordmark: 24px tall on phones, 28px on desktop; reversed version in dark mode (design.md
              section 6). PNG copies of the supplied files (sources in /assets); swap for SVGs when supplied. */}
          <Link to="/" aria-label="Pacifyco home" className="inline-flex shrink-0 py-1 no-underline">
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
    </HeaderBackContext.Provider>
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
