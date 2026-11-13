import { ArrowLeft } from "lucide-react";
import { Link } from "react-router";
import { useHeaderBack } from "../../layouts/headerBack";

// A small link back to the page before, e.g. "← Home". Also shown in the pinned header once the page
// is scrolled (layouts/headerBack.ts).
export function BackLink({ to, label }: { to: string; label: string }) {
  useHeaderBack({ to, label });
  return (
    <Link to={to} className="inline-flex items-center gap-2 self-start text-small">
      <ArrowLeft aria-hidden="true" size={18} strokeWidth={1.75} />
      {label}
    </Link>
  );
}
