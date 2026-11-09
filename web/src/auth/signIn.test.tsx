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

const PARENT_CHECKLIST = {
  items: [
    { key: "details", status: "to_do" },
    { key: "consent", status: "to_do" },
    { key: "children", status: "to_do" },
    { key: "emergency_contacts", status: "to_do" },
  ],
  finished: false,
};
const SITTER_CHECKLIST = {
  items: ["details", "profile", "identity_documents", "police_certificate", "references", "psych_test"].map((key) => ({
    key,
    status: "to_do",
  })),
  live: false,
};

function checklistFor(url: string): Response | null {
  if (url.endsWith("/parent/checklist")) return jsonResponse(PARENT_CHECKLIST);
  if (url.endsWith("/sitter/checklist")) return jsonResponse(SITTER_CHECKLIST);
  return null;
}

function meResponse(profile: unknown = null) {
  return (url: string) =>
    Promise.resolve(
      url.endsWith("/me")
        ? jsonResponse({ email: "asha@example.com", profile })
        : (checklistFor(url) ?? jsonResponse({ status: "ok", environment: "local" })),
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

  test("someone with a profile is sent straight to their area", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(
      meResponse({ role: "sitter", status: "pending", full_name: "Asha K" }) as typeof fetch,
    );
    const { router } = renderApp("/");
    await waitFor(() => expect(router.state.location.pathname).toBe("/sitter"));
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
  test("the sign-in page sends signed-in people straight to their area", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(meResponse(PARENT_PROFILE) as typeof fetch);
    const { router } = renderApp("/sign-in");
    await waitFor(() => expect(router.state.location.pathname).toBe("/parent"));
  });

  test("signing out forgets the account and offers sign-in again", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(meResponse(PARENT_PROFILE) as typeof fetch);
    renderApp("/");
    await screen.findByRole("heading", { level: 1, name: "Time for you." });

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("link", { name: "Sign in" })).toBeTruthy();
    expect(fake.auth.signOut).toHaveBeenCalled();
  });
});

describe("joining after the first sign-in", () => {
  type Call = { url: string; init?: RequestInit };

  // GET /me says "no profile yet" until POST /me/profile answers with `created` (or `failure`); after
  // that it returns `created`, like the real API.
  function joinApi(created: unknown, failure?: { status: number; code: string; details?: unknown }) {
    const calls: Call[] = [];
    let me: unknown = { email: "asha@example.com", profile: null };
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url.endsWith("/me/profile")) {
        if (!failure) me = created;
        return Promise.resolve(
          failure
            ? jsonResponse(
                { error: { code: failure.code, message: "Nope", details: failure.details ?? null } },
                failure.status,
              )
            : jsonResponse(created, 201),
        );
      }
      if (url.endsWith("/me")) return Promise.resolve(jsonResponse(me));
      return Promise.resolve(checklistFor(url) ?? jsonResponse({ status: "ok", environment: "local" }));
    }) as typeof fetch);
    return calls;
  }

  async function agreeAndCreate() {
    fireEvent.click(await screen.findByRole("checkbox", { name: /I agree to the/ }));
    fireEvent.click(screen.getByRole("button", { name: /Yes, create my account/ }));
  }

  async function choose(role: RegExp) {
    fireEvent.click(await screen.findByRole("button", { name: role }));
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
  }

  test("a parent chooses, confirms and lands in the parent area: only role and terms are asked", async () => {
    fake.state.session = fake.session;
    const calls = joinApi({ email: "asha@example.com", profile: PARENT_PROFILE });
    const { router } = renderApp("/join");

    await choose(/I'm a parent/);
    expect(screen.getByRole("heading", { name: "You're joining as a parent." })).toBeTruthy();
    expect(screen.queryByLabelText("Full name")).toBeNull();
    expect(screen.queryByLabelText("Mobile number")).toBeNull();
    await agreeAndCreate();

    await waitFor(() => expect(router.state.location.pathname).toBe("/parent"));
    const post = calls.find((call) => call.url.endsWith("/me/profile"))!;
    expect(post.init!.method).toBe("POST");
    expect(JSON.parse(post.init!.body as string)).toEqual({
      role: "parent",
      accepted: [
        { kind: "parent_terms", version: "1.0" },
        { kind: "privacy_policy", version: "0.1-draft" },
      ],
    });
    // Straight into the area; a bubble from the profile button leads to the checklist.
    expect((await screen.findByRole("link", { name: "Finish your profile" }, { timeout: 5000 })).getAttribute("href")).toBe(
      "/parent/profile",
    );
    expect(screen.queryByRole("heading", { name: "Finish your profile" })).toBeNull();
  });

  test("a sitter is asked to confirm being a sitter", async () => {
    fake.state.session = fake.session;
    joinApi({ email: "asha@example.com", profile: { ...PARENT_PROFILE, role: "sitter" } });
    const { router } = renderApp("/join");
    await choose(/I'm a sitter/);
    expect(screen.getByRole("heading", { name: "You're joining as a sitter." })).toBeTruthy();
    await agreeAndCreate();
    await waitFor(() => expect(router.state.location.pathname).toBe("/sitter"));
  });

  test("Go back returns to the role choice without creating anything", async () => {
    fake.state.session = fake.session;
    const calls = joinApi({});
    renderApp("/join");
    await choose(/I'm a parent/);
    fireEvent.click(screen.getByRole("button", { name: "Go back" }));
    expect(screen.getByRole("heading", { name: "How will you use Pacify?" })).toBeTruthy();
    expect(calls.some((call) => call.url.endsWith("/me/profile"))).toBe(false);
  });

  test("a refusal we can't explain asks for a reload", async () => {
    fake.state.session = fake.session;
    joinApi(null, { status: 422, code: "validation_error", details: [{ field: "body.role", message: "x" }] });
    renderApp("/join");
    await choose(/I'm a parent/);
    await agreeAndCreate();
    expect(await screen.findByText(/Please reload the page and try again/)).toBeTruthy();
  });

  test("an email that already has an account explains what to do", async () => {
    fake.state.session = fake.session;
    joinApi(null, { status: 409, code: "email_in_use" });
    renderApp("/join");
    await choose(/I'm a parent/);
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
});

describe("finishing a profile after sign-up", () => {
  type Call = { url: string; init?: RequestInit };

  // A signed-up person with no details yet. PUT /me/details answers with `saved` (or `failure`).
  function detailsApi(role = "parent", failure?: { status: number; code: string; details?: unknown }) {
    fake.state.session = fake.session;
    const calls: Call[] = [];
    const profile = { ...PARENT_PROFILE, role, full_name: null, details_complete: false };
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url.endsWith("/me/details")) {
        if (failure) {
          return Promise.resolve(
            jsonResponse({ error: { code: failure.code, message: "Nope", details: failure.details ?? null } }, failure.status),
          );
        }
        const body = JSON.parse(init!.body as string) as Record<string, string>;
        return Promise.resolve(
          jsonResponse({ email: "asha@example.com", profile: { ...profile, ...body, details_complete: true } }),
        );
      }
      if (url.endsWith("/me")) return Promise.resolve(jsonResponse({ email: "asha@example.com", profile }));
      if (url.endsWith("/service-area")) return Promise.resolve(jsonResponse({ pin_codes: ["560001", "560034"] }));
      return Promise.resolve(checklistFor(url) ?? jsonResponse({ status: "ok", environment: "local" }));
    }) as typeof fetch);
    return calls;
  }

  async function fill(name: string, phone: string, pinCode = "560034", address = "12, 4th Cross, Koramangala") {
    fireEvent.change(await screen.findByLabelText("Full name"), { target: { value: name } });
    fireEvent.change(screen.getByLabelText("Mobile number"), { target: { value: phone } });
    fireEvent.change(screen.getByLabelText("Home pin code"), { target: { value: pinCode } });
    fireEvent.change(screen.getByLabelText("Home address"), { target: { value: address } });
    fireEvent.click(screen.getByRole("button", { name: /Save my details/ }));
  }

  test("the parent's profile page lists what's left, each linking to where it's done", async () => {
    detailsApi();
    renderApp("/parent/profile");
    expect(await screen.findByText("Finish these to book a sitter.")).toBeTruthy();
    const links = {
      "Your details": "/parent/details",
      "Parental consent": "/parent/consent",
      "Your children": "/parent/family",
      "Emergency contacts": "/parent/family",
    };
    for (const [name, href] of Object.entries(links)) {
      expect(screen.getByRole("link", { name: new RegExp(name) }).getAttribute("href")).toBe(href);
    }
  });

  test("a finished parent profile says booking waits for the birth certificates", async () => {
    detailsApi();
    vi.mocked(fetch).mockImplementation(((url: string) =>
      Promise.resolve(
        url.endsWith("/parent/checklist")
          ? jsonResponse({
              items: PARENT_CHECKLIST.items.map((item) => ({
                ...item,
                status: item.key === "children" ? "waiting" : "done",
              })),
              finished: true,
            })
          : jsonResponse({ email: "asha@example.com", profile: PARENT_PROFILE }),
      )) as typeof fetch);
    renderApp("/parent/profile");
    expect(await screen.findByText(/a booking is confirmed once Pacify has checked/i)).toBeTruthy();
    expect(within(screen.getByRole("link", { name: /Your children/ })).getByText("Being checked")).toBeTruthy();
  });

  test("the sitter's profile page lists every onboarding step", async () => {
    detailsApi("sitter");
    renderApp("/sitter/profile");
    expect(await screen.findByText(/once every step passes and Pacify approves your profile/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Your details/ }).getAttribute("href")).toBe("/sitter/details");
    expect(screen.getByRole("link", { name: /Police clearance certificate/ }).getAttribute("href")).toBe(
      "/sitter/application",
    );
    expect(screen.getByRole("link", { name: /Psychology screening/ }).getAttribute("href")).toBe("/sitter/psych-test");
  });

  test("details are saved and the person goes back to their profile checklist", async () => {
    const calls = detailsApi();
    const { router } = renderApp("/parent/details");
    await fill("Asha K", "98765 43210");
    await waitFor(() => expect(router.state.location.pathname).toBe("/parent/profile"));
    const put = calls.find((call) => call.url.endsWith("/me/details"))!;
    expect(put.init!.method).toBe("PUT");
    expect(JSON.parse(put.init!.body as string)).toEqual({
      full_name: "Asha K",
      phone: "98765 43210",
      pin_code: "560034",
      address: "12, 4th Cross, Koramangala",
    });
  });

  test("a name, an Indian mobile number and an address are needed", async () => {
    const calls = detailsApi();
    renderApp("/parent/details");
    await fill("  ", "12345", "560034", " ");
    expect(screen.getByText("Please tell us your full name.")).toBeTruthy();
    expect(screen.getByText(/That number doesn't look quite right/)).toBeTruthy();
    expect(screen.getByText("Please enter your home address.")).toBeTruthy();
    expect(calls.some((call) => call.url.endsWith("/me/details"))).toBe(false);
  });

  test("a pin code outside the service area is caught before saving", async () => {
    detailsApi("sitter");
    renderApp("/sitter/details");
    // Wait for the service area list, as a person filling the form would.
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).endsWith("/service-area"))).toBe(true));
    await fill("Asha K", "9876543210", "560002");
    expect(
      await screen.findByText("Pacify isn't in 560002 yet. For now we're in these Bengaluru pin codes: 560001, 560034."),
    ).toBeTruthy();
  });

  test("a short pin code is a field error", async () => {
    detailsApi();
    renderApp("/parent/details");
    await fill("Asha K", "9876543210", "5600");
    expect(screen.getByText(/Pin codes have 6 digits/)).toBeTruthy();
  });

  test("if the API refuses the pin code, the form shows it on the pin code field", async () => {
    detailsApi("parent", { status: 422, code: "outside_service_area" });
    renderApp("/parent/details");
    await fill("Asha K", "9876543210", "560034");
    expect(await screen.findByText(/Pacify isn't in 560034 yet/)).toBeTruthy();
  });

  test("if the API refuses a field, the form marks that field", async () => {
    detailsApi("parent", {
      status: 422,
      code: "validation_error",
      details: [{ field: "body.address", message: "Field required" }],
    });
    renderApp("/parent/details");
    await fill("Asha K", "9876543210");
    expect(await screen.findByText("Please enter your home address.")).toBeTruthy();
    expect(screen.queryByText("Nope")).toBeNull();
  });

  test("Google's name prefills the form", async () => {
    detailsApi();
    fake.state.session = { ...fake.session, user: { ...fake.session.user, user_metadata: { full_name: "Asha Kumar" } } };
    renderApp("/parent/details");
    expect(((await screen.findByLabelText("Full name")) as HTMLInputElement).value).toBe("Asha Kumar");
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
  type Status = { version: string; required_accepted: boolean; accepted_at: string | null; marketing: boolean };

  const NOT_ACCEPTED: Status = { version: CONSENT_VERSION, required_accepted: false, accepted_at: null, marketing: false };

  function parentWithConsent(initial: Status, apiVersion = CONSENT_VERSION) {
    fake.state.session = fake.session;
    let current: Status = { ...initial, version: apiVersion };
    const calls: Call[] = [];
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url.endsWith("/parent/consent/marketing")) {
        const { accepted } = JSON.parse(init!.body as string) as { accepted: boolean };
        current = { ...current, marketing: accepted };
        return Promise.resolve(jsonResponse(current));
      }
      if (url.endsWith("/parent/consent")) {
        if (init?.method === "POST") {
          const body = JSON.parse(init.body as string) as { marketing: boolean };
          current = { ...current, required_accepted: true, accepted_at: "2026-11-01T10:00:00Z", marketing: body.marketing };
        }
        return Promise.resolve(jsonResponse(current));
      }
      if (url.endsWith("/parent/checklist")) {
        const items = PARENT_CHECKLIST.items.map((item) =>
          item.key === "consent" ? { ...item, status: current.required_accepted ? "done" : "to_do" } : item,
        );
        return Promise.resolve(jsonResponse({ items, finished: false }));
      }
      if (url.endsWith("/me")) return Promise.resolve(jsonResponse({ email: "asha@example.com", profile: PARENT_PROFILE }));
      return Promise.resolve(jsonResponse({ status: "ok", environment: "local" }));
    }) as typeof fetch);
    return calls;
  }

  async function consentItem() {
    return within(await screen.findByRole("link", { name: /Parental consent/ }));
  }

  test("a parent who hasn't consented is asked to, from their profile page", async () => {
    parentWithConsent(NOT_ACCEPTED);
    renderApp("/parent/profile");
    const link = await screen.findByRole("link", { name: /Parental consent/ });
    expect(link.getAttribute("href")).toBe("/parent/consent");
    expect(within(link).getByText("To do")).toBeTruthy();
  });

  test("the form shows the draft text and needs every required box ticked before agreeing", async () => {
    const calls = parentWithConsent(NOT_ACCEPTED);
    const { router } = renderApp("/parent/consent");
    expect(await screen.findByRole("heading", { level: 1, name: "Parental consent form" })).toBeTruthy();
    expect(screen.getByText("DRAFT — NOT LEGALLY REVIEWED.")).toBeTruthy();
    expect(screen.getByText(`Version ${CONSENT_VERSION}`)).toBeTruthy();

    const required = [
      await screen.findByRole("checkbox", { name: /use of my own data/ }),
      screen.getByRole("checkbox", { name: /use of each child's data/ }),
      screen.getByRole("checkbox", { name: /sharing my child's care details/ }),
      screen.getByRole("checkbox", { name: /emergency authorisation/ }),
    ];
    const marketing = screen.getByRole("checkbox", { name: /offers and updates/ });
    for (const box of [...required, marketing]) expect((box as HTMLInputElement).checked).toBe(false);

    // Ticking only some of the required boxes isn't enough.
    fireEvent.click(required[0]);
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    expect(screen.getByText("Please tick every required box to continue.")).toBeTruthy();
    expect(calls.some((call) => call.init?.method === "POST")).toBe(false);

    for (const box of required.slice(1)) fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    // Back to the profile checklist, where consent is now done.
    await waitFor(() => expect(router.state.location.pathname).toBe("/parent/profile"));
    expect((await consentItem()).getByText("Done")).toBeTruthy();
    const post = calls.find((call) => call.init?.method === "POST")!;
    expect(JSON.parse(post.init!.body as string)).toEqual({ version: CONSENT_VERSION, marketing: false });
  });

  test("ticking the optional marketing box is sent along with the required ones", async () => {
    const calls = parentWithConsent(NOT_ACCEPTED);
    renderApp("/parent/consent");
    fireEvent.click(await screen.findByRole("checkbox", { name: /use of my own data/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /use of each child's data/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /sharing my child's care details/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /emergency authorisation/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /offers and updates/ }));
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));

    expect((await consentItem()).getByText("Done")).toBeTruthy();
    const post = calls.find((call) => call.init?.method === "POST")!;
    expect(JSON.parse(post.init!.body as string)).toEqual({ version: CONSENT_VERSION, marketing: true });
  });

  test("a parent who has consented sees it done on their checklist", async () => {
    parentWithConsent({ version: CONSENT_VERSION, required_accepted: true, accepted_at: "2026-10-30T08:00:00Z", marketing: false });
    renderApp("/parent/profile");
    expect((await consentItem()).getByText("Done")).toBeTruthy();
  });

  test("opening the form again after consenting shows when, the way back, and a marketing toggle", async () => {
    parentWithConsent({ version: CONSENT_VERSION, required_accepted: true, accepted_at: "2026-10-30T08:00:00Z", marketing: false });
    renderApp("/parent/consent");
    expect(await screen.findByText("You gave your consent on 30 Oct 2026.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back to your profile" }).getAttribute("href")).toBe("/parent/profile");

    const marketing = screen.getByRole("checkbox", { name: /offers and updates/ }) as HTMLInputElement;
    expect(marketing.checked).toBe(false);
    fireEvent.click(marketing);
    await waitFor(() => expect((marketing as HTMLInputElement).checked).toBe(true));
  });

  test("an old copy of the form can't be accepted", async () => {
    parentWithConsent(NOT_ACCEPTED, "0.2");
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
      return Promise.resolve(checklistFor(url) ?? jsonResponse({ status: "ok", environment: "local" }));
    }) as typeof fetch);
    return calls;
  }

  async function reachConfirmation(role: RegExp) {
    fireEvent.click(await screen.findByRole("button", { name: role }));
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

  test("a parent agrees to the Family Terms of Use and Privacy policy", async () => {
    joinAs();
    renderApp("/join");
    await reachConfirmation(/I'm a parent/);
    expect(screen.getByRole("checkbox").closest("label")!.textContent).toBe(
      "I agree to the Family Terms of Use and Privacy policy.",
    );
    const label = within(screen.getByRole("checkbox").closest("label")!);
    expect(label.getByRole("link", { name: "Family Terms of Use" }).getAttribute("href")).toBe("/terms/parent");
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

describe("the profile button and its bubble", () => {
  function signedIn(profile: Record<string, unknown>, checklist: unknown) {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(((url: string) =>
      Promise.resolve(
        url.endsWith("/checklist")
          ? jsonResponse(checklist)
          : url.endsWith("/me")
            ? jsonResponse({ email: "asha@example.com", profile })
            : jsonResponse({ status: "ok", environment: "local" }),
      )) as typeof fetch);
  }

  test("with steps left, the home shows a bubble from the profile button instead of the checklist", async () => {
    signedIn(PARENT_PROFILE, PARENT_CHECKLIST);
    renderApp("/parent");
    const bubble = await screen.findByRole("link", { name: "Finish your profile" }, { timeout: 5000 });
    expect(bubble.getAttribute("href")).toBe("/parent/profile");
    expect(screen.getByRole("link", { name: "Your profile" }).getAttribute("href")).toBe("/parent/profile");
    expect(screen.queryByRole("link", { name: /Parental consent/ })).toBeNull();
  });

  test("a rejected step changes what the bubble says", async () => {
    signedIn(
      { ...PARENT_PROFILE, role: "sitter" },
      { ...SITTER_CHECKLIST, items: [{ key: "police_certificate", status: "rejected", reason: "Too old" }] },
    );
    renderApp("/sitter");
    expect((await screen.findByRole("link", { name: "Something needs another look" }, { timeout: 5000 })).getAttribute("href")).toBe(
      "/sitter/profile",
    );
  });

  test("the bubble isn't shown on the profile page itself", async () => {
    signedIn(PARENT_PROFILE, PARENT_CHECKLIST);
    renderApp("/parent/profile");
    expect(await screen.findByRole("heading", { name: "Finish your profile" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Finish your profile" })).toBeNull();
  });

  test("no bubble once nothing is left to do (items only waiting for Pacify count as done)", async () => {
    signedIn(
      { ...PARENT_PROFILE, role: "sitter" },
      { ...SITTER_CHECKLIST, items: SITTER_CHECKLIST.items.map((item) => ({ ...item, status: "waiting" })) },
    );
    renderApp("/sitter");
    expect(await screen.findByRole("link", { name: "Your profile" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Finish your profile" })).toBeNull();
  });

  test("admins have no profile button", async () => {
    signedIn({ ...PARENT_PROFILE, role: "admin", status: "active" }, PARENT_CHECKLIST);
    renderApp("/admin");
    expect(await screen.findByRole("heading", { name: "Admin" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Your profile" })).toBeNull();
  });
});
