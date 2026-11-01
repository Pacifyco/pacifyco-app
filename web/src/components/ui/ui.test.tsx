import { fireEvent, render, screen } from "@testing-library/react";
import { ShieldCheck } from "lucide-react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, test, vi } from "vitest";
import {
  BookingCard,
  Button,
  ButtonLink,
  Card,
  Chip,
  EmergencyButton,
  EmptyState,
  HourBalance,
  IconTile,
  RoleChooser,
  Select,
  SitterCard,
  TextInput,
  Textarea,
  VERIFIED_LABELS,
  VerifiedChip,
  type SitterCardProps,
} from ".";

const withRouter = (ui: ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("Button", () => {
  test("primary is a coral pill with a chocolate label, full width on phones", () => {
    render(<Button>Meet your sitter</Button>);
    const button = screen.getByRole("button", { name: "Meet your sitter" });
    expect(button.className).toContain("bg-coral");
    expect(button.className).toContain("text-on-coral");
    expect(button.className).toContain("rounded-pill");
    expect(button.className).toContain("w-full sm:w-auto");
    expect(button.getAttribute("type")).toBe("button");
  });

  test("the arrow appears only on primary buttons and is hidden from screen readers", () => {
    render(
      <>
        <Button arrow>Next</Button>
        <Button variant="secondary" arrow>
          Back
        </Button>
      </>,
    );
    expect(screen.getByRole("button", { name: "Next" }).textContent).toBe("Next→");
    expect(screen.getByRole("button", { name: "Next" }).querySelector("[aria-hidden]")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Back" }).textContent).toBe("Back");
  });

  test("loading blocks clicks and marks the button busy", () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Save
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Save" });
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
    expect(button.getAttribute("aria-busy")).toBe("true");
  });

  test("secondary and tertiary aren't full width", () => {
    render(
      <>
        <Button variant="secondary">A</Button>
        <Button variant="tertiary">B</Button>
      </>,
    );
    expect(screen.getByRole("button", { name: "A" }).className).toContain("border-strong");
    expect(screen.getByRole("button", { name: "A" }).className).not.toContain("w-full");
    expect(screen.getByRole("button", { name: "B" }).className).toContain("text-coral-deep");
  });

  test("ButtonLink is a link styled as a button", () => {
    withRouter(<ButtonLink to="/sitters/1">Meet Priya first</ButtonLink>);
    const link = screen.getByRole("link", { name: "Meet Priya first" });
    expect(link.getAttribute("href")).toBe("/sitters/1");
    expect(link.className).toContain("rounded-pill");
  });
});

describe("inputs", () => {
  test("label is tied to the input, which is required unless optional", () => {
    render(
      <>
        <TextInput label="Full name" />
        <TextInput label="Second parent's name" optional />
      </>,
    );
    expect(screen.getByLabelText("Full name").hasAttribute("required")).toBe(true);
    expect(screen.getByLabelText(/Second parent's name/).hasAttribute("required")).toBe(false);
    expect(screen.getByText("(optional)")).toBeTruthy();
  });

  test("an error is announced with the field and shown with an icon", () => {
    render(<TextInput label="Email" error="That email doesn't look quite right — could you check it?" hint="We'll send a code" />);
    const input = screen.getByLabelText("Email");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    const describedBy = input.getAttribute("aria-describedby")!.split(" ");
    const texts = describedBy.map((id) => document.getElementById(id)!.textContent);
    expect(texts).toEqual(["We'll send a code", "That email doesn't look quite right — could you check it?"]);
    expect(document.getElementById(describedBy[1]!)!.querySelector("svg")).toBeTruthy();
  });

  test("select and textarea follow the same rules", () => {
    render(
      <>
        <Select label="Pin code" error="Choose a pin code">
          <option>560034</option>
        </Select>
        <Textarea label="Routines" optional />
      </>,
    );
    expect(screen.getByLabelText("Pin code").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByLabelText("Pin code").className).toContain("rounded-pill");
    expect(screen.getByLabelText(/Routines/).className).toContain("rounded-md");
  });
});

describe("chips", () => {
  test("Chip is a pill with ink text", () => {
    render(<Chip>Storytime</Chip>);
    expect(screen.getByText("Storytime").className).toContain("rounded-pill");
  });

  test("VerifiedChip uses fixed wording with a trust-green tick", () => {
    render(<VerifiedChip check="id_police" />);
    const chip = screen.getByText("ID & police verified");
    expect(chip.className).toContain("text-trust");
    expect(chip.querySelector("svg")).toBeTruthy();
  });

  test("verified labels only claim checks Pacify does", () => {
    const labels = Object.values(VERIFIED_LABELS).join(" ").toLowerCase();
    for (const claim of ["address", "plus", "100%", "vetted", "background"]) {
      expect(labels).not.toContain(claim);
    }
  });
});

describe("Card and IconTile", () => {
  test("Card padding options", () => {
    render(
      <>
        <Card>compact</Card>
        <Card padding="roomy">roomy</Card>
      </>,
    );
    expect(screen.getByText("compact").className).toContain("p-5");
    expect(screen.getByText("roomy").className).toContain("p-6");
    expect(screen.getByText("roomy").className).toContain("shadow-soft");
  });

  test("IconTile always shows its label", () => {
    render(<IconTile icon={ShieldCheck} label="ID & police checks" />);
    expect(screen.getByText("ID & police checks")).toBeTruthy();
  });
});

const sitter: SitterCardProps = {
  name: "Priya Raman",
  firstName: "Priya",
  yearsExperience: 6,
  area: "Indiranagar",
  ageGroups: ["Ages 1–8"],
  interests: ["Storytime"],
  checks: ["id_police", "first_aid"],
  rating: 4.8,
  reviewCount: 23,
  familiesServed: 14,
  unlocked: false,
  actionHref: "/sitters/priya",
};

describe("SitterCard", () => {
  test("shows who, checks, experience and the meet-first action", () => {
    withRouter(<SitterCard {...sitter} />);
    expect(screen.getByRole("heading", { name: "Priya Raman" })).toBeTruthy();
    expect(screen.getByText("6 years' experience · Indiranagar")).toBeTruthy();
    expect(screen.getByText("ID & police verified")).toBeTruthy();
    expect(screen.getByText("Trusted by 14 Pacify families")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Meet Priya first" }).getAttribute("href")).toBe("/sitters/priya");
  });

  test("never shows a price", () => {
    const { container } = withRouter(<SitterCard {...sitter} />);
    expect(container.textContent).not.toMatch(/₹|\/hour|rate/i);
  });

  test("unlocked pairs get 'Choose a time'", () => {
    withRouter(<SitterCard {...sitter} unlocked />);
    expect(screen.getByRole("link", { name: "Choose a time" })).toBeTruthy();
  });

  test("new sitters show initials, no rating and no family count", () => {
    const { container } = withRouter(
      <SitterCard {...sitter} rating={null} reviewCount={0} familiesServed={0} yearsExperience={1} />,
    );
    expect(screen.getByText("PR")).toBeTruthy();
    expect(screen.getByText("New to Pacify")).toBeTruthy();
    expect(screen.getByText("1 year's experience · Indiranagar")).toBeTruthy();
    expect(container.textContent).not.toContain("Trusted by");
  });
});

describe("BookingCard", () => {
  test("shows the time in India and who is caring for whom", () => {
    render(
      <BookingCard
        startsAt={new Date("2026-10-10T04:30:00Z")}
        endsAt={new Date("2026-10-10T07:30:00Z")}
        sitterFirstName="Priya"
        childNames={["Asha", "Rohan", "Meera"]}
      />,
    );
    expect(screen.getByText("Next booking")).toBeTruthy();
    expect(screen.getByText("Sat, 10 Oct · 10:00 am – 1:00 pm")).toBeTruthy();
    expect(screen.getByText("Priya is looking after Asha, Rohan and Meera at home.")).toBeTruthy();
  });
});

describe("HourBalance", () => {
  test("shows hours per child, nearest expiry and carried-forward hours", () => {
    render(
      <HourBalance
        balances={[
          { childName: "Asha", units: 25, nearestExpiry: new Date("2026-11-12T06:00:00Z"), carriedForwardUnits: 4 },
          { childName: "Rohan", units: 2, nearestExpiry: null, carriedForwardUnits: 2 },
        ]}
      />,
    );
    expect(screen.getByText("12.5 hours left")).toBeTruthy();
    expect(screen.getByText("Next expiry: 12 Nov 2026")).toBeTruthy();
    expect(screen.getByText("Includes 2 hours carried forward, which don't expire")).toBeTruthy();
    expect(screen.getByText("1 hour left")).toBeTruthy();
    expect(screen.getAllByText(/Next expiry/)).toHaveLength(1);
  });
});

describe("RoleChooser", () => {
  test("offers parent and sitter only, and reports the choice", () => {
    const onChange = vi.fn();
    render(<RoleChooser value="parent" onChange={onChange} />);
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(screen.getByRole("button", { name: /I'm a parent/ }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: /I'm a sitter/ }));
    expect(onChange).toHaveBeenCalledWith("sitter");
  });
});

describe("EmergencyButton", () => {
  test("needs a second step before anything is sent", () => {
    const onConfirm = vi.fn();
    render(<EmergencyButton onConfirm={onConfirm} />);
    const button = screen.getByRole("button", { name: "Emergency or report" });
    expect(button.className).toContain("bg-surface-inverse");
    expect(button.className).not.toContain("bg-coral");

    fireEvent.click(button);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog", { name: "Alert the Pacify team now?" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Yes, alert Pacify" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  test("cancel goes back without sending", () => {
    const onConfirm = vi.fn();
    render(<EmergencyButton onConfirm={onConfirm} />);
    fireEvent.click(screen.getByRole("button", { name: "Emergency or report" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Emergency or report" })).toBeTruthy();
  });

  test("while sending, buttons are blocked", () => {
    render(<EmergencyButton onConfirm={() => {}} sending />);
    fireEvent.click(screen.getByRole("button", { name: "Emergency or report" }));
    expect(screen.getByRole("button", { name: "Alerting the team…" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Cancel" }).hasAttribute("disabled")).toBe(true);
  });
});

describe("EmptyState", () => {
  test("one line and one action", () => {
    render(<EmptyState message="Some days, there just aren't enough of you to go around." action={<Button>Meet a sitter</Button>} />);
    expect(screen.getByText("Some days, there just aren't enough of you to go around.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Meet a sitter" })).toBeTruthy();
  });
});
