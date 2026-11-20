// Overtime requests (CLAUDE.md 6.8; decided 2026-11-12): during the booking the parent asks for extra
// whole hours; the sitter accepts or declines once they've agreed it between them. Nothing is charged
// here -- overtime is worked out at check-out either way.

export type OvertimeRequest = {
  id: string;
  hours: number;
  status: "pending" | "accepted" | "declined";
  requested_at: string;
  decided_at: string | null;
};
