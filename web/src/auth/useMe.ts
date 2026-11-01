import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import { useAuth } from "./AuthProvider";

// Mirrors GET /me (api/app/routers/auth.py).
export type Role = "parent" | "sitter" | "admin";
export const AREA_PATH: Record<Role, string> = { parent: "/parent", sitter: "/sitter", admin: "/admin" };

export type TermsKind = "parent_terms" | "sitter_terms" | "privacy_policy";
export type TermsVersion = { kind: TermsKind; version: string };

export type Me = {
  email: string | null;
  /** Null until the person finishes sign-up. */
  profile: { role: Role; status: "pending" | "active" | "suspended" | "removed"; full_name: string } | null;
  /** Current terms they still have to accept. */
  terms_to_accept?: TermsVersion[];
};

export function useMe() {
  const { status, userId } = useAuth();
  return useQuery({
    queryKey: ["me", userId],
    queryFn: () => apiFetch<Me>("/me"),
    enabled: status === "signed_in",
  });
}
