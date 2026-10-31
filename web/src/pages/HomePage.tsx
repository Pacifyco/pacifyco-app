import { Link } from "react-router";
import { config } from "../config";

export function HomePage() {
  return (
    <section className="max-w-[62ch]">
      <h1>A little help for you. A little more fun for them.</h1>
      <p className="mt-4 text-body-lg text-muted">Pacify is getting ready for families in Bengaluru.</p>

      {/* Temporary links for development until sign-in and role routing land (phase 2). */}
      {config.environment !== "production" && (
        <nav aria-label="Areas" className="mt-6 flex flex-wrap gap-4 text-ui">
          <Link to="/parent">Parent area</Link>
          <Link to="/sitter">Sitter area</Link>
          <Link to="/admin">Admin area</Link>
          <Link to="/dev/components">Components</Link>
        </nav>
      )}
    </section>
  );
}
