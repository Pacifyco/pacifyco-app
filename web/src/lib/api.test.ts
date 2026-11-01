import { describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../test/renderApp";
import { ApiError, apiFetch } from "./api";
import { shouldRetry } from "./queryClient";

describe("apiFetch", () => {
  test("returns JSON from the API base URL", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ status: "ok" }));
    await expect(apiFetch("/health")).resolves.toEqual({ status: "ok" });
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("http://localhost:8000/health");
  });

  test("sends JSON headers when there is a body", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({}));
    await apiFetch("/x", { method: "POST", body: JSON.stringify({ a: 1 }) });
    const headers = vi.mocked(fetch).mock.calls[0][1]!.headers as Headers;
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("Accept")).toBe("application/json");
  });

  test("returns nothing for 204", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiFetch("/x")).resolves.toBeUndefined();
  });

  test("turns the API error format into an ApiError", async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        { error: { code: "slot_taken", message: "That time is already booked", details: { slot: "10:00" } } },
        409,
      ),
    );
    const error = await apiFetch("/x").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 409,
      code: "slot_taken",
      message: "That time is already booked",
      details: { slot: "10:00" },
    });
  });

  test("a non-JSON error becomes a generic ApiError", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response("<html>Bad gateway</html>", { status: 502 }));
    await expect(apiFetch("/x")).rejects.toMatchObject({ status: 502, code: "unexpected_response" });
  });

  test("a network failure becomes a network_error", async () => {
    await expect(apiFetch("/x")).rejects.toMatchObject({ status: 0, code: "network_error" });
  });
});

describe("query retries", () => {
  test("never retries 4xx answers", () => {
    expect(shouldRetry(0, new ApiError(404, "not_found", "Not found"))).toBe(false);
    expect(shouldRetry(0, new ApiError(422, "validation_error", "Fix"))).toBe(false);
  });

  test("retries server and network errors twice", () => {
    const serverError = new ApiError(500, "internal_error", "Oops");
    expect(shouldRetry(0, serverError)).toBe(true);
    expect(shouldRetry(1, serverError)).toBe(true);
    expect(shouldRetry(2, serverError)).toBe(false);
    expect(shouldRetry(0, new ApiError(0, "network_error", "Offline"))).toBe(true);
  });
});
