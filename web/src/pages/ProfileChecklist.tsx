import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Circle, CircleCheck, CircleX, Clock } from "lucide-react";
import { Link } from "react-router";
import { Card } from "../components/ui";
import { cx } from "../components/ui/cx";
import { apiFetch } from "../lib/api";

// "Finish your profile" (CLAUDE.md 6.13). Mirrors GET /parent/checklist and GET /sitter/checklist
// (api/app/services/checklists.py).

export type ItemStatus = "to_do" | "waiting" | "done" | "approved" | "rejected";
type Item = { key: string; status: ItemStatus; reason?: string | null };
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

type Step = { label: string; hint: string; to: string };

export const PARENT_STEPS: Record<string, Step> = {
  details: { label: "Your details", hint: "Name, mobile, pin code and home address", to: "/parent/details" },
  consent: { label: "Parental consent", hint: "Read and accept the consent form", to: "/parent/consent" },
  children: { label: "Your children", hint: "Add each child with their birth certificate", to: "/parent/family" },
  emergency_contacts: { label: "Emergency contacts", hint: "Two people we can call", to: "/parent/family" },
};

export const SITTER_STEPS: Record<string, Step> = {
  details: { label: "Your details", hint: "Name, mobile, pin code and home address", to: "/sitter/details" },
  profile: { label: "About you", hint: "Your profile, health disclosure and payout details", to: "/sitter/application" },
  identity_documents: { label: "ID documents", hint: "Government ID and college or work ID", to: "/sitter/application" },
  police_certificate: { label: "Police clearance certificate", hint: "Upload your certificate", to: "/sitter/application" },
  references: { label: "References", hint: "Two people who know your work", to: "/sitter/application" },
  psych_test: { label: "Psychology screening", hint: "Questions to answer in the app", to: "/sitter/psych-test" },
};

// design.md 12: status is trust or danger with words, never colour alone.
const STATUS: Record<ItemStatus, { word: string; icon: typeof Circle; tone: string }> = {
  to_do: { word: "To do", icon: Circle, tone: "text-muted" },
  waiting: { word: "Being checked", icon: Clock, tone: "text-muted" },
  done: { word: "Done", icon: CircleCheck, tone: "text-trust" },
  approved: { word: "Approved", icon: CircleCheck, tone: "text-trust" },
  rejected: { word: "Needs another look", icon: CircleX, tone: "text-danger" },
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
        {items.map(({ key, status, reason }) => {
          const step = steps[key];
          if (!step) return null;
          const { word, icon: Icon, tone } = STATUS[status];
          return (
            <li key={key} className="border-t border-line first:border-t-0">
              <Link to={step.to} className="flex items-center gap-3 py-3 text-ink no-underline">
                <Icon aria-hidden="true" size={22} strokeWidth={1.75} className={cx("shrink-0", tone)} />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="text-ui">{step.label}</span>
                  <span className="text-small text-muted">{step.hint}</span>
                  {status === "rejected" && reason && (
                    <span className="mt-1 text-small text-danger">Reason: {reason}</span>
                  )}
                </span>
                <span className={cx("text-small", tone)}>{word}</span>
                <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-muted" />
              </Link>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
