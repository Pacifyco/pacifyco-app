import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { Button, LoadingScreen, TextInput } from "../components/ui";
import { supabase } from "../lib/supabase";

type SupabaseError = { status?: number; name?: string };

const NETWORK = "We couldn't reach Pacifyco. Check your connection and try again.";
const EMAIL_NEEDED = "Enter your email to continue.";
const EMAIL_INCOMPLETE = "Enter a full email, like name@gmail.com.";

/** Checked when they press the button, so the button is never greyed out (UX review 2026-11-13). */
export function emailProblem(email: string): string | undefined {
  const value = email.trim();
  if (!value) return EMAIL_NEEDED;
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return EMAIL_INCOMPLETE;
  return undefined;
}

/** Google's "G", in Google's colours, as their sign-in button guidelines ask. */
function GoogleMark() {
  return (
    <svg aria-hidden="true" width="18" height="18" viewBox="0 0 48 48">
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"
      />
      <path
        fill="#FF3D00"
        d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"
      />
    </svg>
  );
}

// supabase-js names every 5xx "AuthRetryableFetchError" too, so only status 0 means no connection.
function isNetworkError(error: SupabaseError): boolean {
  return !error.status;
}

function sendCodeMessage(error: SupabaseError): string {
  if (isNetworkError(error)) return NETWORK;
  if (error.status === 429) return "We've just sent you a code. Please wait a minute before asking for another.";
  if (error.status === 400 || error.status === 422) return "That email doesn't look quite right — could you check it?";
  return "We couldn't send a code just now. Please try again in a moment.";
}

function verifyCodeMessage(error: SupabaseError): string {
  if (isNetworkError(error)) return NETWORK;
  if (error.status === 429) return "That's a few tries in a row. Please wait a minute, then try again.";
  return "That code didn't work. It may have expired — you can ask for a new one below.";
}

/** Where "Sign in" leads: the home page with the sign-in box open. There's no separate sign-in page
(Reuben, 2026-11-13); the old /sign-in address redirects here. */
export const SIGN_IN_PATH = "/?signin";

// The sign-in box on the home page: email code or Google. New people get an account the first time
// they sign in; choosing a role comes next. `autoFocus` puts the cursor in the email field when the
// box opens.
export function SignInBox({ autoFocus = false }: { autoFocus?: boolean }) {
  const { status } = useAuth();
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  if (status === "signed_in") return <Navigate to="/" replace />;

  if (!supabase) {
    return (
      <section className="mx-auto max-w-[28rem] rounded-lg bg-surface-raised p-5 text-center shadow-soft sm:p-6">
        <h2 className="text-h3">Sign in to Pacifyco.</h2>
        <p className="mt-3 text-muted">Sign-in isn't set up in this environment yet.</p>
      </section>
    );
  }
  const auth = supabase.auth;

  async function sendCode(event?: FormEvent) {
    event?.preventDefault();
    const problem = emailProblem(email);
    if (problem) return setError(problem);
    setBusy(true);
    setError(undefined);
    const { error: failure } = await auth.signInWithOtp({ email: email.trim(), options: { shouldCreateUser: true } });
    setBusy(false);
    if (failure) return setError(sendCodeMessage(failure));
    setCode("");
    setStep("code");
  }

  async function verifyCode(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    const { error: failure } = await auth.verifyOtp({ email: email.trim(), token: code, type: "email" });
    setBusy(false);
    // On success the auth listener sees the new session and this page sends them on.
    if (failure) setError(verifyCodeMessage(failure));
  }

  async function continueWithGoogle() {
    setBusy(true);
    setError(undefined);
    const { error: failure } = await auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
    // On success the browser leaves for Google, so only a failure lands here.
    if (failure) {
      setBusy(false);
      setError(
        isNetworkError(failure) ? NETWORK : "Google sign-in isn't available just now. You can use your email instead.",
      );
    }
  }

  return (
    <section
      aria-labelledby="sign-in-heading"
      className="mx-auto w-full max-w-[28rem] rounded-lg bg-surface-raised p-5 text-left shadow-soft sm:p-6"
    >
      <div>
        <div>
          <h2 id="sign-in-heading" className="text-h3">
            Sign in to Pacifyco.
          </h2>

          {step === "email" ? (
            <>
              <p className="mt-2 text-muted">New to Pacifyco? This creates your account too.</p>
              <form onSubmit={sendCode} className="mt-6 flex flex-col gap-5 text-left" noValidate>
                <TextInput
                  label="Email"
                  type="email"
                  name="email"
                  autoComplete="email"
                  inputMode="email"
                  autoFocus={autoFocus}
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  hint="We'll email you a code to sign in."
                  error={error}
                />
                <Button type="submit" arrow fullWidthOnPhone={false} className="w-full" loading={busy}>
                  Email me a code
                </Button>
              </form>
              <div className="my-5 flex items-center gap-3 text-small text-muted" aria-hidden="true">
                <span className="h-px flex-1 bg-line" />
                or
                <span className="h-px flex-1 bg-line" />
              </div>
              <Button variant="secondary" className="w-full" onClick={continueWithGoogle} disabled={busy}>
                <GoogleMark />
                Continue with Google
              </Button>
            </>
          ) : (
            <>
              <p className="mt-2 text-muted">
                We've sent a code to <span className="text-ink">{email.trim()}</span>. It works for 10 minutes.
              </p>
              <form onSubmit={verifyCode} className="mt-6 flex flex-col gap-5 text-left" noValidate>
                <TextInput
                  label="Code"
                  name="code"
                  autoComplete="one-time-code"
                  inputMode="numeric"
                  maxLength={10}
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                  error={error}
                />
                <Button
                  type="submit"
                  arrow
                  fullWidthOnPhone={false}
                  className="w-full"
                  loading={busy}
                  disabled={code.length < 6}
                >
                  Sign in
                </Button>
              </form>
              <div className="mt-5 flex flex-wrap gap-5">
                <Button variant="tertiary" onClick={() => sendCode()} disabled={busy}>
                  Send a new code
                </Button>
                <Button
                  variant="tertiary"
                  onClick={() => {
                    setStep("email");
                    setError(undefined);
                  }}
                  disabled={busy}
                >
                  Use a different email
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

// Google sends people back here. Supabase reads the one-time code in the address and signs them in.
export function AuthCallbackPage() {
  const { status } = useAuth();
  const location = useLocation();
  const failed = /(^|[?#&])error=/.test(location.search + location.hash);

  if (!failed && status === "signed_in") return <Navigate to="/" replace />;
  if (!failed && status === "loading") return <LoadingScreen message="Signing you in…" />;
  return (
    <section className="mx-auto max-w-[62ch] text-center">
      <h1>We couldn't sign you in.</h1>
      <p className="mt-4 text-muted">The sign-in didn't finish. It's fine to try again.</p>
      <p className="mt-5 text-ui">
        <Link to={SIGN_IN_PATH}>Back to sign in</Link>
      </p>
    </section>
  );
}
