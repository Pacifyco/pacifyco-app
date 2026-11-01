import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { supabase } from "../lib/supabase";

type AuthStatus = "loading" | "signed_out" | "signed_in";

type AuthValue = {
  status: AuthStatus;
  userId: string | null;
  email: string | null;
  /** The name Google gave us, if they signed in with Google. Only used to prefill sign-up. */
  name: string | null;
  /** False when this environment has no Supabase settings, so sign-in can't work. */
  available: boolean;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthValue | null>(null);

type SessionState = Pick<AuthValue, "status" | "userId" | "email" | "name">;
const SIGNED_OUT: SessionState = { status: "signed_out", userId: null, email: null, name: null };

function nameFrom(metadata: Record<string, unknown> | undefined): string | null {
  const name = metadata?.full_name ?? metadata?.name;
  return typeof name === "string" && name.trim() ? name.trim() : null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [session, setSession] = useState<SessionState>(() =>
    supabase ? { ...SIGNED_OUT, status: "loading" } : SIGNED_OUT,
  );

  useEffect(() => {
    if (!supabase) return;
    // Fires once with the stored session (INITIAL_SESSION), then on every sign-in, refresh and sign-out.
    const { data } = supabase.auth.onAuthStateChange((_event, current) => {
      setSession(
        current
          ? {
              status: "signed_in",
              userId: current.user.id,
              email: current.user.email ?? null,
              name: nameFrom(current.user.user_metadata),
            }
          : SIGNED_OUT,
      );
    });
    return () => data.subscription.unsubscribe();
  }, []);

  async function signOut() {
    await supabase?.auth.signOut();
    // Forget everything fetched for this person, so the next person on this device sees none of it.
    queryClient.clear();
  }

  return (
    <AuthContext.Provider value={{ ...session, available: supabase !== null, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
