import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, test } from "vitest";
import { ChecklistCard, SITTER_STEPS } from "./ProfileChecklist";

describe("the finish-your-profile checklist", () => {
  test("a rejected item shows the reason Pacifyco gave", () => {
    render(
      <MemoryRouter>
        <ChecklistCard
          heading="Finish your profile"
          intro="Families can find you once every step passes."
          steps={SITTER_STEPS}
          items={[
            { key: "details", status: "done" },
            { key: "police_certificate", status: "rejected", reason: "It's older than six months" },
          ]}
        />
      </MemoryRouter>,
    );
    const police = within(screen.getByRole("link", { name: /Police clearance certificate/ }));
    expect(police.getByText("Needs another look")).toBeTruthy();
    expect(police.getByText("Reason: It's older than six months")).toBeTruthy();
    expect(within(screen.getByRole("link", { name: /Your details/ })).queryByText(/Reason/)).toBeNull();
  });
});
