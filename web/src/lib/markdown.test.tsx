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

describe("Markdown tables, italics and escapes", () => {
  test("renders a table with a header row", () => {
    render(<Markdown body={"| **Topic** | **Rule** |\n|---|---|\n| Rate | ₹80–₹120 |\n| Pay | 12 hours |"} />);
    expect(screen.getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Topic", "Rule"]);
    expect(screen.getAllByRole("cell").map((cell) => cell.textContent)).toEqual(["Rate", "₹80–₹120", "Pay", "12 hours"]);
  });

  test("italics and backslash escapes", () => {
    render(<Markdown body={"*Last updated: \\[DATE\\]*\n\n2\\. Grievance"} />);
    expect(screen.getByText("Last updated: [DATE]").tagName).toBe("EM");
    expect(screen.getByText("2. Grievance")).toBeTruthy();
  });

  test("list items separated by blank lines form one list", () => {
    render(<Markdown body={"- one;\n\n- two; or\n\n- three."} />);
    expect(screen.getAllByRole("list")).toHaveLength(1);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });
});
