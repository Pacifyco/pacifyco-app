import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { Button, TextInput } from "../components/ui";
import { supabase } from "../lib/supabase";

type SupabaseError = { status?: number; name?: string };

const NETWORK = "We couldn't reach Pacify. Check your connection and try again.";

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

// Email code or Google. New people get an account the first time they sign in; choosing a role
// comes next.
export function SignInPage() {
  const { status } = useAuth();
  const [step, setStep] = useState<"email" | "code">("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  if (status === "signed_in") return <Navigate to="/" replace />;

  if (!supabase) {
    return (
      <section className="max-w-[62ch]">
        <h1>Sign in to Pacify.</h1>
        <p className="mt-4 text-muted">Sign-in isn't set up in this environment yet.</p>
      </section>
    );
  }
  const auth = supabase.auth;

  async function sendCode(event?: FormEvent) {
    event?.preventDefault();
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
    <section className="max-w-[28rem]">
      <h1>Sign in to Pacify.</h1>

      {step === "email" ? (
        <>
          <p className="mt-4 text-muted">New to Pacify? This creates your account too.</p>
          <form onSubmit={sendCode} className="mt-6 flex flex-col gap-5" noValidate>
            <TextInput
              label="Email"
              type="email"
              name="email"
              autoComplete="email"
              inputMode="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              hint="We'll email you a code to sign in."
              error={error}
            />
            <Button type="submit" arrow loading={busy} disabled={!email.trim()}>
              Email me a code
            </Button>
          </form>
          <p className="my-5 text-small text-muted">or</p>
          <Button variant="secondary" onClick={continueWithGoogle} disabled={busy}>
            Continue with Google
          </Button>
        </>
      ) : (
        <>
          <p className="mt-4 text-muted">
            We've sent a code to <span className="text-ink">{email.trim()}</span>. It works for 10 minutes.
          </p>
          <form onSubmit={verifyCode} className="mt-6 flex flex-col gap-5" noValidate>
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
            <Button type="submit" arrow loading={busy} disabled={code.length < 6}>
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
    </section>
  );
}

// Google sends people back here. Supabase reads the one-time code in the address and signs them in.
export function AuthCallbackPage() {
  const { status } = useAuth();
  const location = useLocation();
  const failed = /(^|[?#&])error=/.test(location.search + location.hash);

  if (!failed && status === "signed_in") return <Navigate to="/" replace />;
  if (!failed && status === "loading") {
    return (
      <section className="max-w-[62ch]" aria-live="polite">
        <p className="text-muted">Signing you in…</p>
      </section>
    );
  }
  return (
    <section className="max-w-[62ch]">
      <h1>We couldn't sign you in.</h1>
      <p className="mt-4 text-muted">The sign-in didn't finish. It's fine to try again.</p>
      <p className="mt-5 text-ui">
        <Link to="/sign-in">Back to sign in</Link>
      </p>
    </section>
  );
}
