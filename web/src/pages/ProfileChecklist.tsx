import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Circle, CircleCheck, CircleX, Clock } from "lucide-react";
import { Link } from "react-router";
import { Card } from "../components/ui";
import { cx } from "../components/ui/cx";
import { apiFetch } from "../lib/api";

// "Finish your profile" (CLAUDE.md 6.13). Mirrors GET /parent/checklist and GET /sitter/checklist
// (api/app/services/checklists.py).

export type ItemStatus = "to_do" | "waiting" | "done" | "approved" | "rejected";
/** `note` is the exact next action, e.g. "1 child · certificate needed" or "Add your photo". */
type Item = { key: string; status: ItemStatus; reason?: string | null; note?: string | null };
export type ParentChecklist = { items: Item[]; finished: boolean };
export type SitterChecklist = { items: Item[]; live: boolean; application_rejected_reason?: string | null };

export function useChecklist<T extends ParentChecklist | SitterChecklist>(role: "parent" | "sitter") {
  // Always fresh when the profile page opens: it reflects changes made on many other pages. The header's
  // profile button shares this query, so its "finish your profile" bubble updates at the same time.
  return useQuery({ queryKey: ["checklist", role], queryFn: () => apiFetch<T>(`/${role}/checklist`), staleTime: 0 });
}

/** What the profile button's bubble says, or null when there's nothing for the person to do. */
export function profilePrompt(items: Item[]): string | null {
  if (items.some((item) => item.status === "rejected")) return "Something needs another look";
  if (items.some((item) => item.status === "to_do")) return "Finish your profile";
  return null;
}

/** `to` can depend on what's missing: each row opens the exact step to finish (UX review 2026-11-13). */
type Step = { label: string; hint: string; to: string | ((note?: string | null) => string) };

export const PARENT_STEPS: Record<string, Step> = {
  consent: { label: "Parental consent", hint: "Read and accept the consent form and our terms", to: "/parent/consent" },
  details: { label: "Your details", hint: "Name, mobile, pin code and home address", to: "/parent/details" },
  children: { label: "Your children", hint: "Add each child with their birth certificate", to: "/parent/family" },
  emergency_contacts: { label: "Emergency contacts", hint: "Two people we can call", to: "/parent/family?step=emergency" },
};

const APPLICATION = "/sitter/application";

export const SITTER_STEPS: Record<string, Step> = {
  consent: { label: "Sitter consent", hint: "Read our guidelines and accept our terms", to: "/sitter/consent" },
  details: { label: "Your details", hint: "Name, mobile, pin code and home address", to: "/sitter/details" },
  profile: {
    label: "About you",
    hint: "Your profile, photo and payout details",
    to: (note) =>
      note?.includes("photo")
        ? `${APPLICATION}?step=documents`
        : note?.includes("paid")
          ? `${APPLICATION}?step=payout`
          : `${APPLICATION}?step=profile`,
  },
  identity_documents: {
    label: "ID documents",
    hint: "Upload your government ID and a college or work ID",
    to: `${APPLICATION}?step=documents`,
  },
  police_certificate: {
    label: "Police clearance certificate",
    hint: "Upload your certificate",
    to: `${APPLICATION}?step=documents`,
  },
  references: { label: "References", hint: "Add two people who know your work", to: `${APPLICATION}?step=references` },
  psych_test: { label: "Psychology screening", hint: "Questions to answer in the app", to: "/sitter/psych-test" },
};

// design.md 12: status is trust or danger with words, never colour alone; "waiting" is muted on sunken.
const STATUS: Record<ItemStatus, { word: string; icon: typeof Circle; tone: string; pill: string }> = {
  to_do: { word: "To do", icon: Circle, tone: "text-muted", pill: "border border-line text-muted" },
  waiting: { word: "In review", icon: Clock, tone: "text-muted", pill: "bg-surface-sunken text-ink" },
  done: { word: "Done", icon: CircleCheck, tone: "text-trust", pill: "border border-trust text-trust" },
  approved: { word: "Approved", icon: CircleCheck, tone: "text-trust", pill: "border border-trust text-trust" },
  rejected: { word: "Needs another look", icon: CircleX, tone: "text-danger", pill: "border border-danger text-danger" },
};

export function ChecklistCard({
  heading,
  intro,
  items,
  steps,
}: {
  heading: string;
  intro: string;
  items: Item[];
  steps: Record<string, Step>;
}) {
  return (
    <Card as="section" className="text-left" aria-labelledby="checklist-heading">
      <h1 id="checklist-heading" className="text-h3">
        {heading}
      </h1>
      <p className="mt-2 text-small text-muted">{intro}</p>
      <ul className="mt-2">
        {items.map(({ key, status, reason, note }) => {
          const step = steps[key];
          if (!step) return null;
          const { word, icon: Icon, tone, pill } = STATUS[status];
          const to = typeof step.to === "function" ? step.to(note) : step.to;
          const finished = status === "done" || status === "approved";
          return (
            <li key={key} className="border-t border-line first:border-t-0">
              <Link to={to} className="flex items-start gap-3 py-3 text-ink no-underline">
                <Icon aria-hidden="true" size={22} strokeWidth={1.75} className={cx("mt-0.5 shrink-0", tone)} />
                <span className="flex min-w-0 flex-1 flex-col items-start gap-1">
                  <span className="text-ui">{step.label}</span>
                  {/* The status sits under the name, so the name keeps the row's width on a phone. */}
                  <span className={cx("rounded-pill px-2 py-px text-caption font-medium", pill)}>{word}</span>
                  <span className="text-small text-muted">{note && !finished ? note : step.hint}</span>
                  {status === "rejected" && reason && <span className="text-small text-danger">Reason: {reason}</span>}
                </span>
                <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} className="mt-0.5 shrink-0 text-muted" />
              </Link>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
