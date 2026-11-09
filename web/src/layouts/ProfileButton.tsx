import { CircleUserRound } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link, useLocation } from "react-router";
import { PROFILE_PATH, useMe } from "../auth/useMe";
import {
  profilePrompt,
  useChecklist,
  type ParentChecklist,
  type SitterChecklist,
} from "../pages/ProfileChecklist";

// The header's profile button (parents and sitters). While something is left to do, a small speech
// bubble comes out of it saying so, instead of the checklist taking up the home page.
export function ProfileButton() {
  const me = useMe();
  const role = me.data?.profile?.role;
  if (role !== "parent" && role !== "sitter") return null;
  return <ProfileButtonFor role={role} />;
}

function ProfileButtonFor({ role }: { role: "parent" | "sitter" }) {
  const checklist = useChecklist<ParentChecklist | SitterChecklist>(role);
  const { pathname } = useLocation();
  // Steps are finished on many pages; check again on every page change so the bubble stays right.
  // (The first page is skipped: the query has only just loaded.)
  const { refetch } = checklist;
  const firstPage = useRef(true);
  useEffect(() => {
    if (firstPage.current) {
      firstPage.current = false;
      return;
    }
    void refetch();
  }, [pathname, refetch]);
  const to = PROFILE_PATH[role];
  const prompt = checklist.isSuccess ? profilePrompt(checklist.data.items ?? []) : null;
  const showBubble = prompt !== null && pathname !== to;

  return (
    <div className="relative">
      <Link
        to={to}
        aria-label="Your profile"
        title="Your profile"
        className="relative flex size-[40px] items-center justify-center rounded-pill border border-line text-ink no-underline transition-colors duration-200 ease-calm hover:bg-surface-tint"
      >
        <CircleUserRound aria-hidden="true" size={24} strokeWidth={1.75} />
        {prompt && (
          <span
            aria-hidden="true"
            className="absolute -right-0.5 -top-0.5 size-3 rounded-pill border-2 border-surface-raised bg-coral"
          />
        )}
      </Link>
      {showBubble && (
        <Link
          to={to}
          className="bubble-in absolute right-0 top-full z-20 mt-3 whitespace-nowrap rounded-md bg-coral px-4 py-2 text-small font-medium text-on-coral no-underline shadow-lift"
        >
          {/* The bubble's tail, pointing up at the button. */}
          <span
            aria-hidden="true"
            className="absolute -top-1.5 right-3.5 size-3 rotate-45 bg-coral"
          />
          <span className="relative">{prompt}</span>
        </Link>
      )}
    </div>
  );
}
