import { CalendarHeart, House, ShieldCheck, Sparkles } from "lucide-react";
import { useState, type ReactNode } from "react";
import {
  BookingCard,
  Button,
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
  VerifiedChip,
  type ChosenRole,
} from "../components/ui";

// Preview of every UI component (design.md section 10). Not available in production.
// Use the theme switch in the header to check both themes.

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-4 border-t border-line pt-6">
      <h2 className="text-h3">{title}</h2>
      {children}
    </section>
  );
}

const inThreeDays = (hour: number) => {
  const date = new Date();
  date.setDate(date.getDate() + 3);
  date.setHours(hour, 0, 0, 0);
  return date;
};

export function ComponentsPage() {
  const [role, setRole] = useState<ChosenRole | null>(null);
  const [alerted, setAlerted] = useState(false);

  return (
    <div className="flex flex-col gap-7">
      <header className="flex flex-col gap-2">
        <p className="text-eyebrow text-muted uppercase">Development only</p>
        <h1>Components</h1>
        <p className="text-muted">Every building block from design.md section 10, with sample content.</p>
      </header>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-4">
          <Button arrow>Meet your sitter</Button>
          <Button variant="secondary">See how it works</Button>
          <Button variant="tertiary">Become a sitter</Button>
          <Button loading>Saving</Button>
          <Button variant="secondary" disabled>
            Not available
          </Button>
        </div>
      </Section>

      <Section title="Inputs">
        <div className="grid max-w-[480px] gap-5">
          <TextInput label="Full name" autoComplete="name" />
          <TextInput
            label="Email"
            type="email"
            defaultValue="priya@example"
            error="That email doesn't look quite right — could you check it?"
          />
          <TextInput label="Second parent's name" optional hint="Only if they'll be meeting sitters too." />
          <Select label="Pin code" defaultValue="">
            <option value="" disabled>
              Choose your pin code
            </option>
            <option>560034</option>
            <option>560038</option>
          </Select>
          <Textarea label="Routines" optional placeholder="Naps, meals, favourite stories" />
        </div>
      </Section>

      <Section title="Chips">
        <div className="flex flex-wrap gap-2">
          <Chip>Ages 1–8</Chip>
          <Chip tone="sunken">Storytime</Chip>
          <VerifiedChip check="id_police" />
          <VerifiedChip check="references" />
          <VerifiedChip check="interview" />
          <VerifiedChip check="first_aid" />
        </div>
      </Section>

      <Section title="Cards and icon tiles">
        <div className="grid gap-5 sm:grid-cols-2">
          <Card>
            <p>Compact card: space-5 padding.</p>
          </Card>
          <Card padding="roomy">
            <p>Roomy card: space-6 padding.</p>
          </Card>
        </div>
        <div className="flex flex-wrap gap-6">
          <IconTile icon={ShieldCheck} label="ID & police checks" />
          <IconTile icon={CalendarHeart} label="Meet first, free" />
          <IconTile icon={House} label="Care at home" />
          <IconTile icon={Sparkles} label="Play and learning" />
        </div>
      </Section>

      <Section title="Sitter cards">
        <div className="grid gap-5 md:grid-cols-2">
          <SitterCard
            name="Priya Raman"
            firstName="Priya"
            yearsExperience={6}
            area="Indiranagar"
            ageGroups={["Ages 1–8"]}
            interests={["Storytime", "Art"]}
            checks={["id_police", "references", "interview", "first_aid"]}
            rating={4.8}
            reviewCount={23}
            familiesServed={14}
            unlocked={false}
            actionHref="/dev/components"
          />
          <SitterCard
            name="Anjali Das"
            firstName="Anjali"
            yearsExperience={1}
            area="Koramangala"
            ageGroups={["Ages 2–5"]}
            interests={["Music"]}
            checks={["id_police", "references", "interview"]}
            rating={null}
            reviewCount={0}
            familiesServed={0}
            unlocked
            actionHref="/dev/components"
          />
        </div>
      </Section>

      <Section title="Booking card and hour balance">
        <div className="grid gap-5 md:grid-cols-2">
          <BookingCard
            startsAt={inThreeDays(10)}
            endsAt={inThreeDays(13)}
            sitterFirstName="Priya"
            childNames={["Asha", "Rohan"]}
          />
          <HourBalance
            balances={[
              { childName: "Asha", units: 25, nearestExpiry: inThreeDays(0), carriedForwardUnits: 4 },
              { childName: "Rohan", units: 4, nearestExpiry: null, carriedForwardUnits: 4 },
            ]}
          />
        </div>
      </Section>

      <Section title="Role chooser">
        <RoleChooser value={role} onChange={setRole} />
      </Section>

      <Section title="Emergency button">
        <div className="max-w-[480px]">
          {alerted ? (
            <p className="text-trust">Preview only: the Pacify team would now be alerted.</p>
          ) : (
            <EmergencyButton onConfirm={() => setAlerted(true)} />
          )}
        </div>
      </Section>

      <Section title="Empty state">
        <EmptyState
          message="Some days, there just aren't enough of you to go around."
          action={<Button variant="secondary">Meet a sitter</Button>}
        />
      </Section>
    </div>
  );
}
