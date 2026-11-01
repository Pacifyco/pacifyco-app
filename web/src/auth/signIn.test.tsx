import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse, renderApp } from "../test/renderApp";

// A stand-in for Supabase Auth: tests decide what each call returns and when the session changes.
const fake = vi.hoisted(() => {
  type Session = { access_token: string; user: { id: string; email: string } };
  type Listener = (event: string, session: Session | null) => void;
  const listeners = new Set<Listener>();
  const state = { session: null as Session | null };
  const emit = (event: string, session: Session | null) => {
    state.session = session;
    for (const listener of listeners) listener(event, session);
  };
  const auth = {
    onAuthStateChange: (listener: Listener) => {
      listeners.add(listener);
      queueMicrotask(() => listener("INITIAL_SESSION", state.session));
      return { data: { subscription: { unsubscribe: () => listeners.delete(listener) } } };
    },
    signInWithOtp: vi.fn(),
    verifyOtp: vi.fn(),
    signInWithOAuth: vi.fn(),
    signOut: vi.fn(async () => {
      emit("SIGNED_OUT", null);
      return { error: null };
    }),
  };
  const session: Session = { access_token: "test-access-token", user: { id: "user-1", email: "asha@example.com" } };
  return { auth, state, emit, listeners, session };
});

vi.mock("../lib/supabase", () => ({
  supabase: { auth: fake.auth },
  getAccessToken: async () => fake.state.session?.access_token ?? null,
}));

beforeEach(() => {
  fake.state.session = null;
  fake.listeners.clear();
  vi.clearAllMocks();
});

function meResponse(profile: unknown = null) {
  return (url: string) =>
    Promise.resolve(
      url.endsWith("/me")
        ? jsonResponse({ email: "asha@example.com", profile })
        : jsonResponse({ status: "ok", environment: "local" }),
    );
}

async function enterEmail(email = "asha@example.com") {
  fireEvent.change(await screen.findByLabelText("Email"), { target: { value: email } });
  fireEvent.click(screen.getByRole("button", { name: /Email me a code/ }));
}

describe("sign in with an email code", () => {
  test("sends a code, checks it, then shows who's signed in using the API", async () => {
    vi.mocked(fetch).mockImplementation(meResponse() as typeof fetch);
    fake.auth.signInWithOtp.mockResolvedValue({ error: null });
    fake.auth.verifyOtp.mockImplementation(async () => {
      fake.emit("SIGNED_IN", fake.session);
      return { error: null };
    });
    const { router } = renderApp("/sign-in");

    await enterEmail(" asha@example.com ");
    expect(await screen.findByText(/We've sent a code to/)).toBeTruthy();
    expect(fake.auth.signInWithOtp).toHaveBeenCalledWith({
      email: "asha@example.com",
      options: { shouldCreateUser: true },
    });

    fireEvent.change(screen.getByLabelText("Code"), { target: { value: "12 34-56" } });
    fireEvent.click(screen.getByRole("button", { name: /Sign in/ }));

    expect(await screen.findByText("You're signed in as asha@example.com.")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/");
    expect(fake.auth.verifyOtp).toHaveBeenCalledWith({ email: "asha@example.com", token: "123456", type: "email" });
    const meCall = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/me"))!;
    expect((meCall[1]!.headers as Headers).get("Authorization")).toBe("Bearer test-access-token");
    expect(screen.getByText(/whether you're a parent or a sitter/)).toBeTruthy();
  });

  test("someone with a profile is offered their area", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(
      meResponse({ role: "sitter", status: "pending", full_name: "Asha K" }) as typeof fetch,
    );
    renderApp("/");
    const link = await screen.findByRole("link", { name: /Go to your account/ });
    expect(link.getAttribute("href")).toBe("/sitter");
  });

  test("asking for codes too often gets a calm message", async () => {
    fake.auth.signInWithOtp.mockResolvedValue({ error: { status: 429, name: "AuthApiError" } });
    renderApp("/sign-in");
    await enterEmail();
    expect(await screen.findByText(/Please wait a minute before asking for another/)).toBeTruthy();
  });

  test("an email Supabase refuses is a blame-free field error", async () => {
    fake.auth.signInWithOtp.mockResolvedValue({ error: { status: 400, name: "AuthApiError" } });
    renderApp("/sign-in");
    await enterEmail("not-an-email");
    expect(await screen.findByText("That email doesn't look quite right — could you check it?")).toBeTruthy();
  });

  test("a wrong or expired code can be retried", async () => {
    fake.auth.signInWithOtp.mockResolvedValue({ error: null });
    fake.auth.verifyOtp.mockResolvedValue({ error: { status: 403, name: "AuthApiError" } });
    renderApp("/sign-in");
    await enterEmail();
    fireEvent.change(await screen.findByLabelText("Code"), { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: /Sign in/ }));
    expect(await screen.findByText(/That code didn't work/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Send a new code" }));
    await waitFor(() => expect(fake.auth.signInWithOtp).toHaveBeenCalledTimes(2));
  });

  test("a server failure (e.g. email sending) isn't called a connection problem", async () => {
    fake.auth.signInWithOtp.mockResolvedValue({ error: { status: 500, name: "AuthRetryableFetchError" } });
    renderApp("/sign-in");
    await enterEmail();
    expect(await screen.findByText("We couldn't send a code just now. Please try again in a moment.")).toBeTruthy();
  });

  test("no connection says so", async () => {
    fake.auth.signInWithOtp.mockResolvedValue({ error: { status: 0, name: "AuthRetryableFetchError" } });
    renderApp("/sign-in");
    await enterEmail();
    expect(await screen.findByText(/We couldn't reach Pacify/)).toBeTruthy();
  });
});

describe("sign in with Google", () => {
  test("goes to Google and comes back to the callback page", async () => {
    fake.auth.signInWithOAuth.mockResolvedValue({ error: null });
    renderApp("/sign-in");
    fireEvent.click(await screen.findByRole("button", { name: "Continue with Google" }));
    await waitFor(() =>
      expect(fake.auth.signInWithOAuth).toHaveBeenCalledWith({
        provider: "google",
        options: { redirectTo: `${window.location.origin}/auth/callback` },
      }),
    );
  });

  test("the callback sends a signed-in person home", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(meResponse() as typeof fetch);
    const { router } = renderApp("/auth/callback?code=abc");
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });

  test("a cancelled or failed Google sign-in explains and links back", async () => {
    renderApp("/auth/callback?error=access_denied&error_description=denied");
    expect(await screen.findByRole("heading", { name: "We couldn't sign you in." })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back to sign in" })).toBeTruthy();
    expect(screen.queryByText(/denied/)).toBeNull(); // provider text isn't echoed
  });
});

describe("signed-in state", () => {
  test("the sign-in page sends signed-in people home", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(meResponse() as typeof fetch);
    const { router } = renderApp("/sign-in");
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });

  test("signing out forgets the account and offers sign-in again", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(meResponse() as typeof fetch);
    renderApp("/");
    await screen.findByText("You're signed in as asha@example.com.");

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeTruthy();
    expect(fake.auth.signOut).toHaveBeenCalled();
    expect(screen.queryByText(/You're signed in/)).toBeNull();
  });
});
