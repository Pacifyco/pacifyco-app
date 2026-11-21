import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../test/renderApp";
import { ChatPage, ChatsPage, type Chat, type ChatSummary } from "./ChatPages";

// Chat between a parent and a sitter (CLAUDE.md 6.11).

const CHAT: Chat = {
  other_id: "s1",
  other_name: "Lakshmi",
  can_send: true,
  messages: [
    { id: "m1", from_me: true, body: "Hi Lakshmi! Asha naps at 2.", created_at: "2030-01-06T05:00:00Z" },
    { id: "m2", from_me: false, body: "Thanks, noted.", created_at: "2030-01-06T05:02:00Z" },
  ],
};

function renderChat(first: Chat, afterSend?: Chat, path = "/parent/chats/s1") {
  const posted: { url: string; body: unknown }[] = [];
  let current = first;
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push({ url, body: JSON.parse(init.body as string) });
      current = afterSend ?? first;
      return Promise.resolve(jsonResponse(current, 201));
    }
    return Promise.resolve(jsonResponse(current));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/parent/chats/:otherId" element={<ChatPage role="parent" />} />
          <Route path="/sitter/chats/:otherId" element={<ChatPage role="sitter" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return posted;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("A chat", () => {
  test("shows both sides and sends a message", async () => {
    const sent = { id: "m3", from_me: true, body: "See you Friday", created_at: "2030-01-06T05:05:00Z" };
    const posted = renderChat(CHAT, { ...CHAT, messages: [...CHAT.messages, sent] });
    expect(await screen.findByRole("heading", { name: "Lakshmi" })).toBeTruthy();
    expect(screen.getByText("Hi Lakshmi! Asha naps at 2.")).toBeTruthy();
    expect(screen.getByText("Thanks, noted.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Your message"), { target: { value: "  See you Friday " } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("See you Friday")).toBeTruthy();
    expect(posted).toEqual([{ url: expect.stringMatching(/\/parent\/chats\/s1$/), body: { body: "See you Friday" } }]);
    expect((screen.getByLabelText("Your message") as HTMLTextAreaElement).value).toBe("");
  });

  test("closed: read only", async () => {
    renderChat({ ...CHAT, can_send: false });
    expect(await screen.findByText("This chat is closed. It opens again when you have another booking together.")).toBeTruthy();
    expect(screen.queryByLabelText("Your message")).toBeNull();
  });

  test("a sitter is told she never has to share her number", async () => {
    renderChat({ ...CHAT, other_name: "Priya" }, undefined, "/sitter/chats/p1");
    expect(await screen.findByText("You never have to share your phone number.")).toBeTruthy();
  });
});

describe("Messages", () => {
  test("each conversation, with the last message", async () => {
    const list: ChatSummary[] = [
      { other_id: "s1", other_name: "Lakshmi", last_body: "Thanks, noted.", last_at: "2030-01-06T05:02:00Z", last_from_me: false, can_send: true },
    ];
    vi.mocked(fetch).mockImplementation((() => Promise.resolve(jsonResponse(list))) as unknown as typeof fetch);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ChatsPage role="parent" />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const row = (await screen.findByText("Lakshmi")).closest("a")!;
    expect(row.getAttribute("href")).toBe("/parent/chats/s1");
    expect(screen.getByText("Thanks, noted.")).toBeTruthy();
  });
});
