import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import { useAuth } from "./AuthProvider";

// Mirrors GET /me (api/app/routers/auth.py).
export type Role = "parent" | "sitter" | "admin";
export type Me = {
  email: string | null;
  /** Null until the person finishes sign-up. */
  profile: { role: Role; status: "pending" | "active" | "suspended" | "removed"; full_name: string } | null;
};

export function useMe() {
  const { status, userId } = useAuth();
  return useQuery({
    queryKey: ["me", userId],
    queryFn: () => apiFetch<Me>("/me"),
    enabled: status === "signed_in",
  });
}
