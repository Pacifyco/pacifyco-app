import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import { useAuth } from "./AuthProvider";

// Mirrors GET /me (api/app/routers/auth.py).
export type Role = "parent" | "sitter" | "admin";
export const AREA_PATH: Record<Role, string> = { parent: "/parent", sitter: "/sitter", admin: "/admin" };
/** "Your profile": the finish-your-profile checklist, opened from the header's profile button. */
export const PROFILE_PATH = { parent: "/parent/profile", sitter: "/sitter/profile" } as const;

export type TermsKind = "parent_terms" | "sitter_terms" | "privacy_policy";
export type TermsVersion = { kind: TermsKind; version: string };

export type MeProfile = {
  role: Role;
  status: "pending" | "active" | "suspended" | "removed";
  /** Name, mobile, pin code and address are asked for in the area after sign-up (CLAUDE.md 6.13). */
  full_name: string | null;
  phone?: string | null;
  pin_code?: string | null;
  address?: string | null;
  details_complete?: boolean;
};

export type Me = {
  email: string | null;
  /** Null until the person finishes sign-up. */
  profile: MeProfile | null;
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
