import { formatBookingTime, joinNames } from "../../lib/format";
import { Card } from "./Card";

// design.md section 10: eyebrow, date and time, then "[Sitter] is looking after [child] at home."
type BookingCardProps = {
  startsAt: Date;
  endsAt: Date;
  sitterFirstName: string;
  childNames: string[];
  eyebrow?: string;
};

export function BookingCard({ startsAt, endsAt, sitterFirstName, childNames, eyebrow = "Next booking" }: BookingCardProps) {
  return (
    <Card as="article" className="flex flex-col gap-2">
      <p className="text-eyebrow text-muted uppercase">{eyebrow}</p>
      <p className="text-h3">{formatBookingTime(startsAt, endsAt)}</p>
      <p className="text-body text-ink">
        {sitterFirstName} is looking after {joinNames(childNames)} at home.
      </p>
    </Card>
  );
}
