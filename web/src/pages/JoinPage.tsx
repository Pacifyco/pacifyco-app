import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { AREA_PATH, useMe, type Me } from "../auth/useMe";
import { termsReady } from "../auth/TermsAgreement";
import { AuthHero, Button, LoadingScreen, RoleChooser, type ChosenRole } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";

type SignUp = { role: ChosenRole };

// After the first sign-in: parent or sitter, then a confirmation, because people can't change their role
// themselves later. Nothing else is asked here: the terms are ticked on the consent page (decided
// 2026-11-12), and name, mobile, pin code and address are "finish your profile" prompts in the area
// (CLAUDE.md 6.13).
export function JoinPage() {
  const { status, userId } = useAuth();
  const me = useMe();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [role, setRole] = useState<ChosenRole | null>(null);

  const signUp = useMutation({
    mutationFn: (body: SignUp) => apiFetch<Me>("/me/profile", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (created) => queryClient.setQueryData(["me", userId], created),
    onError: (error) => {
      // Already set up (e.g. in another tab): reload who they are, and this page moves them on.
      if (error instanceof ApiError && error.code === "already_signed_up") {
        void queryClient.invalidateQueries({ queryKey: ["me", userId] });
      }
    },
  });

  if (status === "signed_out") return <Navigate to="/sign-in" replace />;
  if (status === "loading" || me.isPending) return <LoadingScreen />;
  if (me.isError) return <p className="text-center text-muted">{me.error.message}</p>;
  if (me.data.profile) return <Navigate to={AREA_PATH[me.data.profile.role]} replace />;

  if (!confirming || !role) {
    return (
      <section className="mx-auto max-w-[72rem]">
        <div className="grid gap-6 lg:grid-cols-[1fr_1.15fr] lg:items-center lg:gap-8">
          <AuthHero
            eyebrow="Trusted by families across Bengaluru"
            heading={
              <>
                Care that's <span className="text-coral-display">met</span>, checked and ready.
              </>
            }
            body="Every sitter is ID and police verified, referenced and screened by Pacify, and you can start with a short booking while you're at home."
            photo="parentsDinnerCouple"
          />
          <div className="mx-auto w-full max-w-[44rem] text-center lg:mx-0 lg:max-w-none lg:text-left">
            <h1>How will you use Pacify?</h1>
            <p className="mt-4 text-muted">Choose one. Each account is either a parent or a sitter.</p>
            <div className="mt-6">
              <RoleChooser value={role} onChange={setRole} />
            </div>
            <div className="mt-6 flex justify-center lg:justify-start">
              <Button
                arrow
                disabled={!role}
                onClick={() => {
                  signUp.reset(); // don't show an earlier attempt's error on the confirmation
                  setConfirming(true);
                }}
              >
                Continue
              </Button>
            </div>
          </div>
        </div>
      </section>
    );
  }

  const roleLabel = role === "parent" ? "a parent" : "a sitter";
  const failure = signUp.error instanceof ApiError ? signUp.error : null;

  // Production can't take sign-ups until every placeholder in that role's terms is filled (CLAUDE.md 7):
  // they'd have no terms to accept on their consent page.
  if (!termsReady(role)) {
    return (
      <section className="mx-auto max-w-[36rem] text-center">
        <h1>{role === "parent" ? "Family" : "Sitter"} sign-up opens soon.</h1>
        <p className="mt-4 text-muted">
          We're finishing the {role === "parent" ? "Family" : "Sitter"} Terms of Use. Please check back soon, or contact
          us at query.pacifyco@gmail.com.
        </p>
        <div className="mt-6 flex justify-center">
          <Button variant="secondary" onClick={() => setConfirming(false)}>
            Go back
          </Button>
        </div>
      </section>
    );
  }

  function createAccount() {
    if (role) signUp.mutate({ role });
  }

  return (
    <section className="mx-auto max-w-[36rem] text-center">
      <h1>You're joining as {roleLabel}.</h1>
      <p className="mt-4 text-muted">Is that right? Once your account is set up, only the Pacify team can change this.</p>
      {failure && failure.code !== "already_signed_up" && (
        <p role="alert" className="mt-4 text-small text-danger">
          {failure.code === "email_in_use"
            ? "This email already has a Pacify account. Please sign in with a different email, or contact us."
            : failure.code === "validation_error"
              ? "Something didn't go through. Please reload the page and try again."
              : failure.message}
        </p>
      )}
      <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:justify-center">
        <Button arrow loading={signUp.isPending} onClick={createAccount}>
          Yes, create my account
        </Button>
        <Button variant="secondary" disabled={signUp.isPending} onClick={() => setConfirming(false)}>
          Go back
        </Button>
      </div>
    </section>
  );
}
