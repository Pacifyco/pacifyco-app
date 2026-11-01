import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { Markdown, parseDocument } from "./markdown";

describe("parseDocument", () => {
  test("reads front matter, with Windows line endings too", () => {
    const doc = parseDocument("---\r\nversion: 1.2\r\ntitle: A: B\r\n---\r\n\r\n# Hello\r\n");
    expect(doc.meta).toEqual({ version: "1.2", title: "A: B" });
    expect(doc.body.trim()).toBe("# Hello");
  });

  test("a document without front matter is all body", () => {
    expect(parseDocument("Just text")).toEqual({ meta: {}, body: "Just text" });
  });
});

describe("Markdown", () => {
  test("renders headings, paragraphs, lists and bold, and never HTML", () => {
    const { container } = render(
      <Markdown body={"# Title\n\n## Part\n\nSome **bold** text\nwrapped.\n\n- one\n- two\n\n<b>not html</b>"} />,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Title" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "Part" })).toBeTruthy();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual(["one", "two"]);
    expect(container.querySelector("b")).toBeNull();
    expect(screen.getByText("<b>not html</b>")).toBeTruthy();
  });
});
