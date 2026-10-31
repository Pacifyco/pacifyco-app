import { Link, useRouteError } from "react-router";

export function NotFoundPage() {
  return (
    <section className="max-w-[62ch]">
      <h1>We couldn't find that page.</h1>
      <p className="mt-4 text-muted">It may have moved, or the link may be incomplete.</p>
      <p className="mt-5 text-ui">
        <Link to="/">Go to the home page</Link>
      </p>
    </section>
  );
}

// Shown when a page throws while rendering. Details go to the console (and Sentry later), not the user.
export function RouteErrorPage() {
  const error = useRouteError();
  console.error(error);

  return (
    <main id="main" className="mx-auto max-w-[62ch] px-4 py-7">
      <h1>Something went wrong on our side.</h1>
      <p className="mt-4 text-muted">Please try again in a moment.</p>
      <p className="mt-5 text-ui">
        <a href="/">Go to the home page</a>
      </p>
    </main>
  );
}
