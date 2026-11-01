import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { CONSENT_VERSION } from "../pages/ConsentPage";
import { jsonResponse, renderApp } from "../test/renderApp";

// A stand-in for Supabase Auth: tests decide what each call returns and when the session changes.
const fake = vi.hoisted(() => {
  type Session = {
    access_token: string;
    user: { id: string; email: string; user_metadata?: Record<string, unknown> };
  };
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

const PARENT_PROFILE = { role: "parent", status: "pending", full_name: "Asha K" };

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
  test("sends a code, checks it, then a new person goes on to join", async () => {
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

    expect(await screen.findByRole("heading", { name: "How will you use Pacify?" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/join");
    expect(fake.auth.verifyOtp).toHaveBeenCalledWith({ email: "asha@example.com", token: "123456", type: "email" });
    const meCall = vi.mocked(fetch).mock.calls.find(([url]) => String(url).endsWith("/me"))!;
    expect((meCall[1]!.headers as Headers).get("Authorization")).toBe("Bearer test-access-token");
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
    vi.mocked(fetch).mockImplementation(meResponse(PARENT_PROFILE) as typeof fetch);
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
    vi.mocked(fetch).mockImplementation(meResponse(PARENT_PROFILE) as typeof fetch);
    const { router } = renderApp("/sign-in");
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });

  test("signing out forgets the account and offers sign-in again", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(meResponse(PARENT_PROFILE) as typeof fetch);
    renderApp("/");
    await screen.findByText("You're signed in as asha@example.com.");

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeTruthy();
    expect(fake.auth.signOut).toHaveBeenCalled();
    expect(screen.queryByText(/You're signed in/)).toBeNull();
  });
});

describe("joining after the first sign-in", () => {
  type Call = { url: string; init?: RequestInit };

  // GET /me says "no profile yet"; POST /me/profile answers with `created` (or `failure`).
  function joinApi(created: unknown, failure?: { status: number; code: string; details?: unknown }) {
    const calls: Call[] = [];
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url.endsWith("/me/profile")) {
        return Promise.resolve(
          failure
            ? jsonResponse(
                { error: { code: failure.code, message: "Nope", details: failure.details ?? null } },
                failure.status,
              )
            : jsonResponse(created, 201),
        );
      }
      if (url.endsWith("/me")) return Promise.resolve(jsonResponse({ email: "asha@example.com", profile: null }));
      if (url.endsWith("/service-area")) return Promise.resolve(jsonResponse({ pin_codes: ["560001", "560034"] }));
      return Promise.resolve(jsonResponse({ status: "ok", environment: "local" }));
    }) as typeof fetch);
    return calls;
  }

  async function agreeAndCreate() {
    fireEvent.click(await screen.findByRole("checkbox", { name: /I agree to the/ }));
    fireEvent.click(screen.getByRole("button", { name: /Yes, create my account/ }));
  }

  async function chooseAndFill(role: RegExp, name: string, phone: string, pinCode = "560034") {
    fireEvent.click(await screen.findByRole("button", { name: role }));
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: name } });
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: phone } });
    fireEvent.change(screen.getByLabelText("Home pin code"), { target: { value: pinCode } });
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
  }

  test("a parent chooses, confirms and lands in the parent area", async () => {
    fake.state.session = fake.session;
    const calls = joinApi({ email: "asha@example.com", profile: PARENT_PROFILE });
    const { router } = renderApp("/join");

    await chooseAndFill(/I'm a parent/, "Asha K", "98765 43210");
    expect(screen.getByRole("heading", { name: "You're joining as a parent." })).toBeTruthy();
    await agreeAndCreate();

    await waitFor(() => expect(router.state.location.pathname).toBe("/parent"));
    const post = calls.find((call) => call.url.endsWith("/me/profile"))!;
    expect(post.init!.method).toBe("POST");
    expect(JSON.parse(post.init!.body as string)).toEqual({
      role: "parent",
      full_name: "Asha K",
      phone: "98765 43210",
      pin_code: "560034",
      accepted: [
        { kind: "parent_terms", version: "0.1-draft" },
        { kind: "privacy_policy", version: "0.1-draft" },
      ],
    });
  });

  test("a sitter is asked to confirm being a sitter", async () => {
    fake.state.session = fake.session;
    joinApi({ email: "asha@example.com", profile: { ...PARENT_PROFILE, role: "sitter" } });
    const { router } = renderApp("/join");
    await chooseAndFill(/I'm a sitter/, "Asha K", "+91 6123456789");
    expect(screen.getByRole("heading", { name: "You're joining as a sitter." })).toBeTruthy();
    await agreeAndCreate();
    await waitFor(() => expect(router.state.location.pathname).toBe("/sitter"));
  });

  test("Go back returns to the role choice without creating anything", async () => {
    fake.state.session = fake.session;
    const calls = joinApi({});
    renderApp("/join");
    await chooseAndFill(/I'm a parent/, "Asha K", "9876543210");
    fireEvent.click(screen.getByRole("button", { name: "Go back" }));
    expect(screen.getByRole("heading", { name: "How will you use Pacify?" })).toBeTruthy();
    expect(calls.some((call) => call.url.endsWith("/me/profile"))).toBe(false);
  });

  test("a name and an Indian mobile number are needed", async () => {
    fake.state.session = fake.session;
    joinApi({});
    renderApp("/join");
    await chooseAndFill(/I'm a parent/, "  ", "12345");
    expect(screen.getByText("Please tell us your full name.")).toBeTruthy();
    expect(screen.getByText(/That number doesn't look quite right/)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /You're joining as/ })).toBeNull();
  });

  test("a pin code outside the service area is caught before confirming", async () => {
    fake.state.session = fake.session;
    joinApi({});
    renderApp("/join");
    // Wait for the service area list, as a person filling the form would.
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/service-area"))).toBe(true));
    await chooseAndFill(/I'm a parent/, "Asha K", "9876543210", "560002");
    expect(
      await screen.findByText("Pacify isn't in 560002 yet. For now we're in these Bengaluru pin codes: 560001, 560034."),
    ).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /You're joining as/ })).toBeNull();
  });

  test("a short pin code is a field error", async () => {
    fake.state.session = fake.session;
    joinApi({});
    renderApp("/join");
    await chooseAndFill(/I'm a parent/, "Asha K", "9876543210", "5600");
    expect(screen.getByText(/Pin codes have 6 digits/)).toBeTruthy();
  });

  test("if the API refuses the pin code, the form shows it on the pin code field", async () => {
    fake.state.session = fake.session;
    joinApi(null, { status: 422, code: "outside_service_area" });
    renderApp("/join");
    await chooseAndFill(/I'm a parent/, "Asha K", "9876543210", "560034");
    await agreeAndCreate();
    expect(await screen.findByText(/Pacify isn't in 560034 yet/)).toBeTruthy();
    expect(screen.getByLabelText("Home pin code")).toBeTruthy();
  });

  test("if the API refuses a field, the form marks that field and clears the old error", async () => {
    fake.state.session = fake.session;
    joinApi(null, {
      status: 422,
      code: "validation_error",
      details: [{ field: "body.pin_code", message: "Field required" }],
    });
    renderApp("/join");
    await chooseAndFill(/I'm a sitter/, "Asha K", "9876543210");
    await agreeAndCreate();

    expect(await screen.findByText("Please enter your home pin code.")).toBeTruthy();
    expect(screen.queryByText("Nope")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    expect(await screen.findByRole("heading", { name: "You're joining as a sitter." })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("a refusal we can't pin to a field asks for a reload", async () => {
    fake.state.session = fake.session;
    joinApi(null, { status: 422, code: "validation_error", details: [{ field: "body.extra", message: "x" }] });
    renderApp("/join");
    await chooseAndFill(/I'm a parent/, "Asha K", "9876543210");
    await agreeAndCreate();
    expect(await screen.findByText(/Please reload the page and try again/)).toBeTruthy();
  });

  test("an email that already has an account explains what to do", async () => {
    fake.state.session = fake.session;
    joinApi(null, { status: 409, code: "email_in_use" });
    renderApp("/join");
    await chooseAndFill(/I'm a parent/, "Asha K", "9876543210");
    await agreeAndCreate();
    expect(await screen.findByText(/This email already has a Pacify account/)).toBeTruthy();
  });

  test("people who have joined skip this page", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(meResponse({ ...PARENT_PROFILE, role: "sitter" }) as typeof fetch);
    const { router } = renderApp("/join");
    await waitFor(() => expect(router.state.location.pathname).toBe("/sitter"));
  });

  test("signed-out people are sent to sign in", async () => {
    const { router } = renderApp("/join");
    await waitFor(() => expect(router.state.location.pathname).toBe("/sign-in"));
  });

  test("Google's name prefills the form", async () => {
    fake.state.session = { ...fake.session, user: { ...fake.session.user, user_metadata: { full_name: "Asha Kumar" } } };
    joinApi({});
    renderApp("/join");
    fireEvent.click(await screen.findByRole("button", { name: /I'm a parent/ }));
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    expect((screen.getByLabelText("Full name") as HTMLInputElement).value).toBe("Asha Kumar");
  });
});

describe("role-gated areas", () => {
  function signedInAs(role: string | null, status = "pending") {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(
      meResponse(role ? { role, status, full_name: "Asha K" } : null) as typeof fetch,
    );
  }

  test.each([
    ["parent", "/parent", "Time for you."],
    ["sitter", "/sitter", "Your work with Pacify."],
    ["admin", "/admin", "Admin"],
  ])("a %s sees their own area", async (role, path, heading) => {
    signedInAs(role);
    renderApp(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeTruthy();
  });

  test.each([
    ["parent", "/sitter", "/parent"],
    ["parent", "/admin", "/parent"],
    ["sitter", "/parent", "/sitter"],
    ["sitter", "/admin", "/sitter"],
    ["admin", "/parent", "/admin"],
  ])("a %s opening %s is sent to %s", async (role, path, home) => {
    signedInAs(role);
    const { router } = renderApp(path);
    await waitFor(() => expect(router.state.location.pathname).toBe(home));
  });

  test("someone who hasn't joined is sent to join", async () => {
    signedInAs(null);
    const { router } = renderApp("/parent");
    await waitFor(() => expect(router.state.location.pathname).toBe("/join"));
  });

  test("a suspended account sees that it's on hold, with how to appeal", async () => {
    signedInAs("sitter", "suspended");
    renderApp("/sitter");
    expect(await screen.findByRole("heading", { name: "Your account is on hold." })).toBeTruthy();
    expect(screen.getByText(/appeal within 15 days/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "query.pacifyco@gmail.com" })).toBeTruthy();
    expect(screen.queryByText("Your work with Pacify.")).toBeNull();
  });

  test("a removed account sees that it's closed, even in another area", async () => {
    signedInAs("parent", "removed");
    renderApp("/admin");
    expect(await screen.findByRole("heading", { name: "This account is closed." })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Admin" })).toBeNull();
  });

  test("a blocked person can still sign out", async () => {
    signedInAs("parent", "suspended");
    renderApp("/parent");
    fireEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeTruthy();
  });
});

describe("parental consent", () => {
  type Call = { url: string; init?: RequestInit };

  function parentWithConsent(acceptedAt: string | null, apiVersion = CONSENT_VERSION) {
    fake.state.session = fake.session;
    const calls: Call[] = [];
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url.endsWith("/parent/consent")) {
        const accepted = init?.method === "POST" ? "2026-11-01T10:00:00Z" : acceptedAt;
        return Promise.resolve(jsonResponse({ version: apiVersion, accepted_at: accepted }));
      }
      if (url.endsWith("/me")) return Promise.resolve(jsonResponse({ email: "asha@example.com", profile: PARENT_PROFILE }));
      return Promise.resolve(jsonResponse({ status: "ok", environment: "local" }));
    }) as typeof fetch);
    return calls;
  }

  test("a parent who hasn't consented is asked to, from their home", async () => {
    parentWithConsent(null);
    renderApp("/parent");
    const link = await screen.findByRole("link", { name: /Read the consent form/ });
    expect(link.getAttribute("href")).toBe("/parent/consent");
  });

  test("the form shows the draft text and needs the box ticked before agreeing", async () => {
    const calls = parentWithConsent(null);
    const { router } = renderApp("/parent/consent");
    expect(await screen.findByRole("heading", { level: 1, name: "Parental consent form" })).toBeTruthy();
    expect(screen.getByText("DRAFT — NOT LEGALLY REVIEWED.")).toBeTruthy();
    expect(screen.getByText(`Version ${CONSENT_VERSION}`)).toBeTruthy();

    const box = (await screen.findByRole("checkbox")) as HTMLInputElement;
    expect(box.checked).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    expect(screen.getByText("Please tick the box to give your consent.")).toBeTruthy();
    expect(calls.some((call) => call.init?.method === "POST")).toBe(false);

    fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    // Back to the parent home, which now shows the date.
    expect(await screen.findByText("Parental consent given on 1 Nov 2026.")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/parent");
    const post = calls.find((call) => call.init?.method === "POST")!;
    expect(JSON.parse(post.init!.body as string)).toEqual({ version: CONSENT_VERSION });
  });

  test("a parent who has consented sees when, with no form to fill", async () => {
    parentWithConsent("2026-10-30T08:00:00Z");
    renderApp("/parent");
    expect(await screen.findByText("Parental consent given on 30 Oct 2026.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Read the consent form/ })).toBeNull();
  });

  test("opening the form again after consenting shows when, and the way home", async () => {
    parentWithConsent("2026-10-30T08:00:00Z");
    renderApp("/parent/consent");
    expect(await screen.findByText("You gave your consent on 30 Oct 2026.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back to your home" }).getAttribute("href")).toBe("/parent");
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  test("an old copy of the form can't be accepted", async () => {
    parentWithConsent(null, "0.2");
    renderApp("/parent/consent");
    expect(await screen.findByText(/This form has been updated. Please reload/)).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  test("sitters don't have a consent form", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(meResponse({ ...PARENT_PROFILE, role: "sitter" }) as typeof fetch);
    const { router } = renderApp("/parent/consent");
    await waitFor(() => expect(router.state.location.pathname).toBe("/sitter"));
  });
});

describe("terms at sign-up and after changes", () => {
  function joinAs() {
    fake.state.session = fake.session;
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url.endsWith("/me/profile")) {
        const body = JSON.parse(init!.body as string);
        return Promise.resolve(
          jsonResponse({ email: "asha@example.com", profile: { ...PARENT_PROFILE, role: body.role } }, 201),
        );
      }
      if (url.endsWith("/me")) return Promise.resolve(jsonResponse({ email: "asha@example.com", profile: null }));
      if (url.endsWith("/service-area")) return Promise.resolve(jsonResponse({ pin_codes: ["560034"] }));
      return Promise.resolve(jsonResponse({ status: "ok", environment: "local" }));
    }) as typeof fetch);
    return calls;
  }

  async function reachConfirmation(role: RegExp) {
    fireEvent.click(await screen.findByRole("button", { name: role }));
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Asha K" } });
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: "9876543210" } });
    fireEvent.change(screen.getByLabelText("Home pin code"), { target: { value: "560034" } });
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    await screen.findByRole("heading", { name: /You're joining as/ });
  }

  test("a sitter must tick to agree to the Sitter Terms and Privacy policy", async () => {
    const calls = joinAs();
    const { router } = renderApp("/join");
    await reachConfirmation(/I'm a sitter/);

    const box = screen.getByRole("checkbox");
    expect(box.closest("label")!.textContent).toBe("I agree to the Sitter Terms of Use and Privacy policy.");
    expect((box as HTMLInputElement).checked).toBe(false);
    const label = within(box.closest("label")!);
    const sitterLink = label.getByRole("link", { name: "Sitter Terms of Use" });
    expect(sitterLink.getAttribute("href")).toBe("/terms/sitter");
    expect(sitterLink.getAttribute("target")).toBe("_blank");
    expect(label.getByRole("link", { name: "Privacy policy" }).getAttribute("href")).toBe("/privacy");

    fireEvent.click(screen.getByRole("button", { name: /Yes, create my account/ }));
    expect(screen.getByText("Please tick the box to agree before you continue.")).toBeTruthy();
    expect(calls.some((call) => call.url.endsWith("/me/profile"))).toBe(false);

    fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: /Yes, create my account/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/sitter"));
    const body = JSON.parse(calls.find((call) => call.url.endsWith("/me/profile"))!.init!.body as string);
    expect(body.accepted).toEqual([
      { kind: "sitter_terms", version: "1.1" },
      { kind: "privacy_policy", version: "0.1-draft" },
    ]);
  });

  test("a parent agrees to the Terms of service and Privacy policy", async () => {
    joinAs();
    renderApp("/join");
    await reachConfirmation(/I'm a parent/);
    expect(screen.getByRole("checkbox").closest("label")!.textContent).toBe(
      "I agree to the Terms of service and Privacy policy.",
    );
    const label = within(screen.getByRole("checkbox").closest("label")!);
    expect(label.getByRole("link", { name: "Terms of service" }).getAttribute("href")).toBe("/terms/parent");
  });

  function signedInNeedingTerms(role: string, toAccept: { kind: string; version: string }[]) {
    fake.state.session = fake.session;
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      const profile = { ...PARENT_PROFILE, role };
      if (url.endsWith("/me/terms")) {
        return Promise.resolve(jsonResponse({ email: "asha@example.com", profile, terms_to_accept: [] }));
      }
      if (url.endsWith("/me")) {
        return Promise.resolve(jsonResponse({ email: "asha@example.com", profile, terms_to_accept: toAccept }));
      }
      return Promise.resolve(jsonResponse({ status: "ok", environment: "local" }));
    }) as typeof fetch);
    return calls;
  }

  test("an existing sitter who hasn't accepted sees the terms right after signing in", async () => {
    const calls = signedInNeedingTerms("sitter", [
      { kind: "sitter_terms", version: "1.1" },
      { kind: "privacy_policy", version: "0.1-draft" },
    ]);
    renderApp("/sitter");
    expect(await screen.findByRole("heading", { name: "Please read and accept our terms." })).toBeTruthy();
    expect(screen.queryByText("Your work with Pacify.")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    expect(screen.getByText("Please tick the box to agree before you continue.")).toBeTruthy();

    fireEvent.click(screen.getByRole("checkbox", { name: /I agree to the Sitter Terms of Use/ }));
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    expect(await screen.findByRole("heading", { name: "Your work with Pacify." })).toBeTruthy();
    const post = calls.find((call) => call.url.endsWith("/me/terms"))!;
    expect(JSON.parse(post.init!.body as string)).toEqual({
      accepted: [
        { kind: "sitter_terms", version: "1.1" },
        { kind: "privacy_policy", version: "0.1-draft" },
      ],
    });
  });

  test("when a new version exists that this copy of the app doesn't have, it asks for a reload", async () => {
    signedInNeedingTerms("parent", [{ kind: "parent_terms", version: "0.2" }]);
    renderApp("/parent");
    expect(await screen.findByText(/Our terms have been updated. Please reload/)).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});
