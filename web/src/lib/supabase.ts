import { createClient } from "@supabase/supabase-js";
import { config } from "../config";

// Sign-in only (email code and Google). Every read and write goes through the API.
// Null when VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY isn't set, e.g. in tests.
export const supabase =
  config.supabaseUrl && config.supabaseKey
    ? createClient(config.supabaseUrl, config.supabaseKey, {
        auth: { flowType: "pkce", persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
      })
    : null;

/** The signed-in person's access token, refreshed by Supabase when needed. */
export async function getAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
