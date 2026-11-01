// Placeholders for each role's area (gated by RequireRole in routes.tsx).

export function ParentHomePage() {
  return (
    <section>
      <h1>Time for you.</h1>
      <p className="mt-4 text-muted">Your bookings, hours and sitters will be here.</p>
    </section>
  );
}

export function SitterHomePage() {
  return (
    <section>
      <h1>Your work with Pacify.</h1>
      <p className="mt-4 text-muted">Your bookings, availability and earnings will be here.</p>
    </section>
  );
}

export function AdminHomePage() {
  return (
    <section>
      <h1>Admin</h1>
      <p className="mt-4 text-muted">Verifications, payments, payouts and incidents will be here.</p>
    </section>
  );
}
