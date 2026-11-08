import { ArrowLeft } from "lucide-react";
import { Link } from "react-router";

// A small link back to the page before, e.g. "← Home".
export function BackLink({ to, label }: { to: string; label: string }) {
  return (
    <Link to={to} className="inline-flex items-center gap-2 self-start text-small">
      <ArrowLeft aria-hidden="true" size={18} strokeWidth={1.75} />
      {label}
    </Link>
  );
}
