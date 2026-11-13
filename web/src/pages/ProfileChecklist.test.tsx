import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, test } from "vitest";
import { ChecklistCard, SITTER_ORDER, SITTER_STEPS } from "./ProfileChecklist";

describe("the finish-your-profile checklist", () => {
  test("a sitter's steps open in order: later ones are locked until the first to do is done", () => {
    render(
      <MemoryRouter>
        <ChecklistCard
          heading="Finish your profile"
          intro="x"
          steps={SITTER_STEPS}
          inOrder
          items={SITTER_ORDER.map((key) => ({ key, status: key === "consent" ? "done" : "to_do" }))}
        />
      </MemoryRouter>,
    );
    // Eight steps (Reuben, 2026-11-13); Your details is next, so it's a link; the rest are locked.
    expect(SITTER_ORDER).toHaveLength(8);
    expect(screen.getByRole("link", { name: /Your details/ }).getAttribute("href")).toBe("/sitter/details");
    expect(screen.queryByRole("link", { name: /About you/ })).toBeNull();
    expect(screen.getAllByText("Opens once the step before it is done")).toHaveLength(6);
  });

  test("a rejected item shows the reason Pacifyco gave", () => {
    render(
      <MemoryRouter>
        <ChecklistCard
          heading="Finish your profile"
          intro="Families can find you once every step passes."
          steps={SITTER_STEPS}
          items={[
            { key: "details", status: "done" },
            { key: "identity_documents", status: "rejected", reason: "It's older than six months" },
          ]}
        />
      </MemoryRouter>,
    );
    const police = within(screen.getByRole("link", { name: /ID verification/ }));
    expect(police.getByText("Needs another look")).toBeTruthy();
    expect(police.getByText("Reason: It's older than six months")).toBeTruthy();
    expect(within(screen.getByRole("link", { name: /Your details/ })).queryByText(/Reason/)).toBeNull();
  });
});
