import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
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
  items: ["details", "consent", "profile", "identity_documents", "police_certificate", "references", "psych_test"].map((key) => ({
    key,
    status: "to_do",
  })),
  live: false,
};

function checklistFor(url: string): Response | null {
  if (url.endsWith("/parent/checklist")) return jsonResponse(PARENT_CHECKLIST);
  if (url.endsWith("/sitter/checklist")) return jsonResponse(SITTER_CHECKLIST);
  // Each area's landing page: Find a sitter (parents) and the sitter's bookings (asks for her availability).
  if (url.includes("/parent/sitters?")) return jsonResponse([]);
  if (url.endsWith("/sitter/availability")) return jsonResponse({ week: [], days_off: [] });
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

    expect(await screen.findByRole("heading", { name: "How will you use Pacifyco?" })).toBeTruthy();
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

  test("an incomplete email is caught on pressing the button, and announced", async () => {
    // UX review 2026-11-13: the button is never greyed out, and the field says what's wrong.
    renderApp("/sign-in");
    expect((await screen.findByRole("button", { name: /Email me a code/ })).hasAttribute("disabled")).toBe(false);
    await enterEmail("");
    expect((await screen.findByRole("alert")).textContent).toBe("Enter your email to continue.");
    await enterEmail("abcabc");
    expect((await screen.findByRole("alert")).textContent).toBe("Enter a full email, like name@gmail.com.");
    expect(fake.auth.signInWithOtp).not.toHaveBeenCalled();
  });

  test("an email Supabase refuses is a blame-free field error", async () => {
    fake.auth.signInWithOtp.mockResolvedValue({ error: { status: 400, name: "AuthApiError" } });
    renderApp("/sign-in");
    await enterEmail("asha@example.invalid");
    expect(await screen.findByText("That email doesn't look quite right — could you check it?")).toBeTruthy();
  });

  test("the sign-in page has no Sign in link in its header, and Google shows its mark", async () => {
    renderApp("/sign-in");
    await screen.findByRole("heading", { name: "Sign in to Pacifyco." });
    expect(screen.queryByRole("link", { name: "Sign in" })).toBeNull();
    expect(screen.getByRole("button", { name: "Continue with Google" }).querySelector("svg")).toBeTruthy();
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
    expect(await screen.findByText(/We couldn't reach Pacifyco/)).toBeTruthy();
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
    await waitFor(() => expect(router.state.location.pathname).toBe("/parent/sitters"));
  });

  test("signing out forgets the account and offers sign-in again", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(meResponse(PARENT_PROFILE) as typeof fetch);
    renderApp("/");
    await screen.findByRole("heading", { level: 1, name: "Find a sitter" });

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in to Pacifyco." })).toBeTruthy();
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

  async function create() {
    fireEvent.click(await screen.findByRole("button", { name: /Yes, create my account/ }));
  }

  async function choose(role: RegExp) {
    fireEvent.click(await screen.findByRole("button", { name: role }));
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
  }

  test("a parent chooses, confirms and lands in the parent area: only the role is asked", async () => {
    fake.state.session = fake.session;
    const calls = joinApi({ email: "asha@example.com", profile: PARENT_PROFILE });
    const { router } = renderApp("/join");

    await choose(/I'm a parent/);
    expect(screen.getByRole("heading", { name: "You're joining as a parent." })).toBeTruthy();
    expect(screen.queryByLabelText("Full name")).toBeNull();
    expect(screen.queryByLabelText("Mobile number")).toBeNull();
    // The terms are ticked on the consent page now (decided 2026-11-12).
    expect(screen.queryByRole("checkbox")).toBeNull();
    await create();

    await waitFor(() => expect(router.state.location.pathname).toBe("/parent/sitters"));
    const post = calls.find((call) => call.url.endsWith("/me/profile"))!;
    expect(post.init!.method).toBe("POST");
    expect(JSON.parse(post.init!.body as string)).toEqual({ role: "parent" });
    // Straight into the area; a bubble from the profile button (and the page) lead to the checklist.
    const links = await screen.findAllByRole("link", { name: "Finish your profile" }, { timeout: 5000 });
    for (const link of links) expect(link.getAttribute("href")).toBe("/parent/profile");
    expect(screen.queryByRole("heading", { name: "Finish your profile" })).toBeNull();
  });

  test("a sitter is asked to confirm being a sitter", async () => {
    fake.state.session = fake.session;
    joinApi({ email: "asha@example.com", profile: { ...PARENT_PROFILE, role: "sitter" } });
    const { router } = renderApp("/join");
    await choose(/I'm a sitter/);
    expect(screen.getByRole("heading", { name: "You're joining as a sitter." })).toBeTruthy();
    await create();
    await waitFor(() => expect(router.state.location.pathname).toBe("/sitter"));
  });

  test("Go back returns to the role choice without creating anything", async () => {
    fake.state.session = fake.session;
    const calls = joinApi({});
    renderApp("/join");
    await choose(/I'm a parent/);
    fireEvent.click(screen.getByRole("button", { name: "Go back" }));
    expect(screen.getByRole("heading", { name: "How will you use Pacifyco?" })).toBeTruthy();
    expect(calls.some((call) => call.url.endsWith("/me/profile"))).toBe(false);
  });

  test("a refusal we can't explain asks for a reload", async () => {
    fake.state.session = fake.session;
    joinApi(null, { status: 422, code: "validation_error", details: [{ field: "body.role", message: "x" }] });
    renderApp("/join");
    await choose(/I'm a parent/);
    await create();
    expect(await screen.findByText(/Please reload the page and try again/)).toBeTruthy();
  });

  test("an email that already has an account explains what to do", async () => {
    fake.state.session = fake.session;
    joinApi(null, { status: 409, code: "email_in_use" });
    renderApp("/join");
    await choose(/I'm a parent/);
    await create();
    expect(await screen.findByText(/This email already has a Pacifyco account/)).toBeTruthy();
  });

  test("people who have joined skip this page", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(meResponse({ ...PARENT_PROFILE, role: "sitter" }) as typeof fetch);
    const { router } = renderApp("/join");
    await waitFor(() => expect(router.state.location.pathname).toBe("/sitter"));
  });

  test("signed-out people are sent to sign in", async () => {
    const { router } = renderApp("/join");
    await waitFor(() => expect(router.state.location.search).toBe("?signin"));
    expect(router.state.location.pathname).toBe("/");
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
      "Emergency contacts": "/parent/family?step=emergency",
    };
    for (const [name, href] of Object.entries(links)) {
      expect(screen.getByRole("link", { name: new RegExp(name) }).getAttribute("href")).toBe(href);
    }
  });

  test("a checklist row shows its status under the name and the exact next action", async () => {
    detailsApi();
    vi.mocked(fetch).mockImplementation(((url: string) =>
      Promise.resolve(
        url.endsWith("/parent/checklist")
          ? jsonResponse({
              items: [{ key: "children", status: "to_do", note: "1 child · certificate needed" }],
              finished: false,
            })
          : jsonResponse({ email: "asha@example.com", profile: PARENT_PROFILE }),
      )) as typeof fetch);
    renderApp("/parent/profile");
    const row = within(await screen.findByRole("link", { name: /Your children/ }));
    expect(row.getByText("To do")).toBeTruthy();
    expect(row.getByText("1 child · certificate needed")).toBeTruthy();
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
    expect(await screen.findByText(/a booking is confirmed once Pacifyco has checked/i)).toBeTruthy();
    expect(within(screen.getByRole("link", { name: /Your children/ })).getByText("In review")).toBeTruthy();
  });

  test("the sitter's profile page lists every onboarding step", async () => {
    detailsApi("sitter");
    renderApp("/sitter/profile");
    expect(await screen.findByText(/once every step passes and Pacifyco approves your profile/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Your details/ }).getAttribute("href")).toBe("/sitter/details");
    // Each row opens the exact step (UX review 2026-11-13).
    expect(screen.getByRole("link", { name: /Police clearance certificate/ }).getAttribute("href")).toBe(
      "/sitter/application?step=documents",
    );
    expect(screen.getByRole("link", { name: /References/ }).getAttribute("href")).toBe(
      "/sitter/application?step=references",
    );
    expect(screen.getByRole("link", { name: /Psychology screening/ }).getAttribute("href")).toBe("/sitter/psych-test");
  });

  test("details are saved and the person goes back to their profile checklist", async () => {
    const calls = detailsApi();
    const { router } = renderApp("/parent/details");
    await fill("Asha K", "98765 43210");
    await waitFor(() => expect(router.state.location.pathname).toBe("/parent/profile"));
    expect(await screen.findByText("Details saved")).toBeTruthy(); // the toast, still up on the profile
    const put = calls.find((call) => call.url.endsWith("/me/details"))!;
    expect(put.init!.method).toBe("PUT");
    expect(JSON.parse(put.init!.body as string)).toEqual({
      full_name: "Asha K",
      phone: "9876543210", // typed after a fixed +91 (UX review 2026-11-13)
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
      await screen.findByText("Pacifyco isn't in 560002 yet. For now we're in these parts of Bengaluru: MG Road (560001), Koramangala (560034)."),
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
    expect(await screen.findByText(/Pacifyco isn't in 560034 yet/)).toBeTruthy();
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
    ["parent", "/parent", "Find a sitter"],
    ["sitter", "/sitter", "Hi Asha."],
    ["admin", "/admin", "Admin"],
  ])("a %s sees their own area", async (role, path, heading) => {
    signedInAs(role);
    renderApp(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeTruthy();
  });

  test("a sitter who isn't live yet sees where her application stands, not an empty bookings list", async () => {
    signedInAs("sitter");
    renderApp("/sitter");
    expect(await screen.findByRole("heading", { name: "Finish your application" })).toBeTruthy();
    expect(screen.getByText(/0 of 7 steps done/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Continue your application/ }).getAttribute("href")).toBe("/sitter/profile");
    expect(screen.queryByText(/No bookings yet/)).toBeNull();
  });

  function liveSitter(week: unknown[]) {
    fake.state.session = fake.session;
    const profile = { role: "sitter", status: "active", full_name: "Asha K", pin_code: "560034" };
    vi.mocked(fetch).mockImplementation(((url: string) =>
      url.endsWith("/sitter/availability")
        ? Promise.resolve(jsonResponse({ week, days_off: [] }))
        : url.endsWith("/sitter/checklist")
          ? Promise.resolve(jsonResponse({ ...SITTER_CHECKLIST, live: true }))
          : meResponse(profile)(url)) as typeof fetch);
  }

  test("an approved sitter is welcomed once, and asked to set her availability", async () => {
    liveSitter([]);
    renderApp("/sitter");
    expect(await screen.findByText("You're approved")).toBeTruthy();
    expect(screen.getByText("Families near 560034 can now find you on Pacifyco.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Get your first booking" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Set your availability/ }).getAttribute("href")).toBe("/sitter/availability");

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByText("You're approved")).toBeNull();
    cleanup();
    renderApp("/sitter");
    await screen.findByRole("heading", { name: "Get your first booking" });
    expect(screen.queryByText("You're approved")).toBeNull(); // only once
  });

  test("a sitter who has set her availability just sees her bookings, and changes it from her profile", async () => {
    liveSitter([{ weekday: 0, start_hour: 9, end_hour: 13 }]);
    renderApp("/sitter");
    expect(await screen.findByText("No bookings yet. Confirmed bookings will show here.")).toBeTruthy();
    expect(screen.getByText(/Your usual week is set/)).toBeTruthy();

    cleanup();
    renderApp("/sitter/profile");
    expect((await screen.findByRole("link", { name: "Change your availability" })).getAttribute("href")).toBe(
      "/sitter/availability",
    );
  });

  test.each([
    ["parent", "/sitter", "/parent/sitters"],
    ["parent", "/admin", "/parent/sitters"],
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
    expect(screen.getByRole("link", { name: "founders@pacifyco.in" })).toBeTruthy();
    expect(screen.queryByText("Your bookings")).toBeNull();
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
    expect(await screen.findByRole("heading", { name: "Sign in to Pacifyco." })).toBeTruthy();
  });
});

describe("parental consent", () => {
  type Call = { url: string; init?: RequestInit };
  type Status = { version: string; required_accepted: boolean; accepted_at: string | null; marketing: boolean };

  const NOT_ACCEPTED: Status = { version: CONSENT_VERSION, required_accepted: false, accepted_at: null, marketing: false };

  const PARENT_TERMS = [
    { kind: "parent_terms", version: "1.0" },
    { kind: "privacy_policy", version: "0.1-draft" },
  ];

  function parentWithConsent(
    initial: Status,
    apiVersion = CONSENT_VERSION,
    termsToAccept: { kind: string; version: string }[] = [],
  ) {
    fake.state.session = fake.session;
    let current: Status = { ...initial, version: apiVersion };
    // The Family Terms and privacy policy are ticked with the consents: outstanding until then.
    let toAccept = initial.required_accepted ? termsToAccept : PARENT_TERMS;
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
          toAccept = [];
        }
        return Promise.resolve(jsonResponse(current));
      }
      if (url.endsWith("/parent/checklist")) {
        const done = current.required_accepted && toAccept.length === 0;
        const items = PARENT_CHECKLIST.items.map((item) =>
          item.key === "consent" ? { ...item, status: done ? "done" : "to_do" } : item,
        );
        return Promise.resolve(jsonResponse({ items, finished: false }));
      }
      if (url.endsWith("/me/terms")) {
        toAccept = [];
        return Promise.resolve(jsonResponse({ email: "asha@example.com", profile: PARENT_PROFILE, terms_to_accept: [] }));
      }
      if (url.endsWith("/me")) {
        return Promise.resolve(
          jsonResponse({ email: "asha@example.com", profile: PARENT_PROFILE, terms_to_accept: toAccept }),
        );
      }
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
    expect(screen.queryByText(/^Version /)).toBeNull(); // no version details (Reuben, 2026-11-13)

    const required = [
      await screen.findByRole("checkbox", { name: /use of my own data/ }),
      screen.getByRole("checkbox", { name: /use of each child's data/ }),
      screen.getByRole("checkbox", { name: /sharing my child's care details/ }),
      screen.getByRole("checkbox", { name: /emergency authorisation/ }),
    ];
    const terms = screen.getByRole("checkbox", { name: /I agree to the Family Terms of Use/ });
    const marketing = screen.getByRole("checkbox", { name: /offers and updates/ });
    for (const box of [...required, terms, marketing]) expect((box as HTMLInputElement).checked).toBe(false);

    // Each box says whether it's required (UX review 2026-11-13: the copy says five, the page shows six).
    expect(screen.getAllByText("Required")).toHaveLength(5);
    expect(screen.getAllByText("Optional").length).toBeGreaterThanOrEqual(1);

    // Ticking only some of the required boxes isn't enough: the first one left gets the focus.
    fireEvent.click(required[0]);
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    expect(screen.getByText("Please tick every required box to continue.")).toBeTruthy();
    expect(document.activeElement).toBe(required[1]);
    expect(required[1]!.closest(".border-danger")).toBeTruthy(); // outlined
    expect(required[0]!.closest(".border-danger")).toBeNull();
    expect(calls.some((call) => call.init?.method === "POST")).toBe(false);

    // Every consent but not the terms: still not enough.
    for (const box of required.slice(1)) fireEvent.click(box);
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    expect(screen.getByText("Please tick every required box to continue.")).toBeTruthy();
    expect(calls.some((call) => call.init?.method === "POST")).toBe(false);

    fireEvent.click(terms);
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    // Back to the profile checklist, where consent is now done.
    await waitFor(() => expect(router.state.location.pathname).toBe("/parent/profile"));
    expect((await consentItem()).getByText("Done")).toBeTruthy();
    const post = calls.find((call) => call.init?.method === "POST")!;
    expect(JSON.parse(post.init!.body as string)).toEqual({
      version: CONSENT_VERSION,
      marketing: false,
      accepted: PARENT_TERMS,
    });
  });

  test("the terms box links to the Family Terms of Use and Privacy policy", async () => {
    parentWithConsent(NOT_ACCEPTED);
    renderApp("/parent/consent");
    const box = await screen.findByRole("checkbox", { name: /I agree to the/ });
    expect(box.closest("label")!.textContent).toBe("I agree to the Family Terms of Use and Privacy policy.");
    const label = within(box.closest("label")!);
    const termsLink = label.getByRole("link", { name: "Family Terms of Use" });
    expect(termsLink.getAttribute("href")).toBe("/terms/parent");
    expect(termsLink.getAttribute("target")).toBe("_blank");
    expect(label.getByRole("link", { name: "Privacy policy" }).getAttribute("href")).toBe("/privacy");
  });

  test("after a new terms version, the consent page asks for just that and sends it", async () => {
    const calls = parentWithConsent(
      { version: CONSENT_VERSION, required_accepted: true, accepted_at: "2026-10-30T08:00:00Z", marketing: false },
      CONSENT_VERSION,
      [{ kind: "privacy_policy", version: "0.1-draft" }],
    );
    const { router } = renderApp("/parent/profile");
    expect((await consentItem()).getByText("To do")).toBeTruthy();

    await router.navigate("/parent/consent");
    expect(await screen.findByText(/updated our terms since then/)).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: /use of my own data/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    expect(screen.getByText("Please tick every required box to continue.")).toBeTruthy();

    fireEvent.click(screen.getByRole("checkbox", { name: /I agree to the Privacy policy/ }));
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/parent/profile"));
    expect((await consentItem()).getByText("Done")).toBeTruthy();
    const post = calls.find((call) => call.url.endsWith("/me/terms"))!;
    expect(JSON.parse(post.init!.body as string)).toEqual({
      accepted: [{ kind: "privacy_policy", version: "0.1-draft" }],
    });
  });

  test("a terms version this copy of the app doesn't have asks for a reload", async () => {
    parentWithConsent(
      { version: CONSENT_VERSION, required_accepted: true, accepted_at: "2026-10-30T08:00:00Z", marketing: false },
      CONSENT_VERSION,
      [{ kind: "parent_terms", version: "0.2" }],
    );
    renderApp("/parent/consent");
    expect(await screen.findByText(/This form has been updated. Please reload/)).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  test("ticking the optional marketing box is sent along with the required ones", async () => {
    const calls = parentWithConsent(NOT_ACCEPTED);
    renderApp("/parent/consent");
    fireEvent.click(await screen.findByRole("checkbox", { name: /use of my own data/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /use of each child's data/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /sharing my child's care details/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /emergency authorisation/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /I agree to the Family Terms of Use/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: /offers and updates/ }));
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));

    expect((await consentItem()).getByText("Done")).toBeTruthy();
    const post = calls.find((call) => call.init?.method === "POST")!;
    expect(JSON.parse(post.init!.body as string)).toEqual({
      version: CONSENT_VERSION,
      marketing: true,
      accepted: PARENT_TERMS,
    });
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

  test("sitters don't have the parental consent form", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(meResponse({ ...PARENT_PROFILE, role: "sitter" }) as typeof fetch);
    const { router } = renderApp("/parent/consent");
    await waitFor(() => expect(router.state.location.pathname).toBe("/sitter"));
  });
});

describe("sitter consent", () => {
  const SITTER_DOCS = [
    { kind: "sitter_consent", version: "1.0" },
    { kind: "sitter_terms", version: "1.1" },
    { kind: "privacy_policy", version: "0.1-draft" },
  ];

  // A signed-up sitter; GET /me lists `toAccept` until POST /me/terms.
  function sitterNeeding(toAccept: { kind: string; version: string }[]) {
    fake.state.session = fake.session;
    const profile = { ...PARENT_PROFILE, role: "sitter" };
    let outstanding = toAccept;
    const calls: { url: string; init?: RequestInit }[] = [];
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url.endsWith("/me/terms")) {
        outstanding = [];
        return Promise.resolve(jsonResponse({ email: "asha@example.com", profile, terms_to_accept: [] }));
      }
      if (url.endsWith("/me")) {
        return Promise.resolve(jsonResponse({ email: "asha@example.com", profile, terms_to_accept: outstanding }));
      }
      if (url.endsWith("/sitter/checklist")) {
        const items = SITTER_CHECKLIST.items.map((item) =>
          item.key === "consent" ? { ...item, status: outstanding.length ? "to_do" : "done" } : item,
        );
        return Promise.resolve(jsonResponse({ ...SITTER_CHECKLIST, items }));
      }
      return Promise.resolve(checklistFor(url) ?? jsonResponse({ status: "ok", environment: "local" }));
    }) as typeof fetch);
    return calls;
  }

  test("a new sitter isn't held up by the terms: she lands in her area, and her profile lists the consent", async () => {
    sitterNeeding(SITTER_DOCS);
    const { router } = renderApp("/sitter");
    expect(await screen.findByRole("heading", { name: "Finish your application" })).toBeTruthy();

    await router.navigate("/sitter/profile");
    const link = await screen.findByRole("link", { name: /Sitter consent/ });
    expect(link.getAttribute("href")).toBe("/sitter/consent");
    expect(within(link).getByText("To do")).toBeTruthy();
  });

  test("the page shows the guidelines and needs both boxes ticked", async () => {
    const calls = sitterNeeding(SITTER_DOCS);
    const { router } = renderApp("/sitter/consent");
    expect(await screen.findByRole("heading", { level: 1, name: "Sitter consent" })).toBeTruthy();
    for (const heading of [
      "Your safety comes first",
      "Money and gifts",
      "Respecting the family’s home",
      "Showing up",
      "Caring for the child",
      "If something goes wrong",
    ]) {
      expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    }
    expect(screen.queryByText(/^Version /)).toBeNull();

    const guidelines = await screen.findByRole("checkbox", { name: "I've read these and I'll follow them." });
    const terms = screen.getByRole("checkbox", { name: /I agree to the Sitter Terms of Use/ });
    expect(terms.closest("label")!.textContent).toBe("I agree to the Sitter Terms of Use and Privacy policy.");
    const label = within(terms.closest("label")!);
    const termsLink = label.getByRole("link", { name: "Sitter Terms of Use" });
    expect(termsLink.getAttribute("href")).toBe("/terms/sitter");
    expect(termsLink.getAttribute("target")).toBe("_blank");
    expect(label.getByRole("link", { name: "Privacy policy" }).getAttribute("href")).toBe("/privacy");

    fireEvent.click(guidelines);
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    expect(screen.getByText("Please tick both boxes to continue.")).toBeTruthy();
    expect(calls.some((call) => call.url.endsWith("/me/terms"))).toBe(false);

    fireEvent.click(terms);
    fireEvent.click(screen.getByRole("button", { name: "I agree" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/sitter/profile"));
    expect(within(await screen.findByRole("link", { name: /Sitter consent/ })).getByText("Done")).toBeTruthy();
    const post = calls.find((call) => call.url.endsWith("/me/terms"))!;
    expect(JSON.parse(post.init!.body as string)).toEqual({ accepted: SITTER_DOCS });
  });

  test("once accepted, the page says so and leads back", async () => {
    sitterNeeding([]);
    renderApp("/sitter/consent");
    expect(await screen.findByText(/You've accepted these/)).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.getByRole("link", { name: "Back to your profile" }).getAttribute("href")).toBe("/sitter/profile");
  });

  test("a version this copy of the app doesn't have asks for a reload", async () => {
    sitterNeeding([{ kind: "sitter_consent", version: "2.0" }]);
    renderApp("/sitter/consent");
    expect(await screen.findByText(/This page has been updated. Please reload/)).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  test("parents don't have the sitter consent page", async () => {
    fake.state.session = fake.session;
    vi.mocked(fetch).mockImplementation(meResponse(PARENT_PROFILE) as typeof fetch);
    const { router } = renderApp("/sitter/consent");
    await waitFor(() => expect(router.state.location.pathname).toBe("/parent/sitters"));
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
            : (checklistFor(url) ?? jsonResponse({ status: "ok", environment: "local" })),
      )) as typeof fetch);
  }

  test("with steps left, the home shows a bubble from the profile button instead of the checklist", async () => {
    signedIn(PARENT_PROFILE, PARENT_CHECKLIST);
    renderApp("/parent");
    // The bubble, and the page's own button (Find a sitter shows no filters until the profile is done).
    const [bubble] = await screen.findAllByRole("link", { name: "Finish your profile" }, { timeout: 5000 });
    expect(bubble!.getAttribute("href")).toBe("/parent/profile");
    expect(bubble!.className).toContain("bubble-in");
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

  test("no bubble once nothing is left to do (items only waiting for Pacifyco count as done)", async () => {
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
