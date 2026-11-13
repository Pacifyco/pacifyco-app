import type { ReactNode } from "react";
import { Photo, type PhotoName } from "./Photo";

type AuthHeroProps = {
  eyebrow: string;
  heading: ReactNode;
  body: string;
  photo: PhotoName;
};

// Decorative split-screen panel for the sign-in and join pages: a gradient ground, two soft blobs
// (design.md's calm, never-bouncy motion applies to nothing here -- they're static), the brand
// promise and a photo. Hidden below `lg` so the form is the first thing people see on a phone.
// Not a heading: the page's own <h1> (e.g. "Sign in to Pacifyco.") is the one real heading on the page.
export function AuthHero({ eyebrow, heading, body, photo }: AuthHeroProps) {
  return (
    <div className="relative hidden flex-col justify-between gap-8 overflow-hidden rounded-lg bg-gradient-to-br from-surface-tint via-surface-sunken to-surface-raised p-8 lg:flex">
      <span
        aria-hidden="true"
        className="absolute -top-16 -right-20 size-[260px] rounded-pill bg-surface-tint opacity-60"
      />
      <span
        aria-hidden="true"
        className="absolute right-16 -bottom-20 size-[180px] rounded-pill border-[22px] border-coral opacity-15"
      />
      <p className="relative text-eyebrow text-muted uppercase">{eyebrow}</p>
      <div className="relative flex flex-col gap-4">
        <p className="text-h1">{heading}</p>
        <p className="max-w-[36ch] text-body-lg text-muted">{body}</p>
      </div>
      <Photo name={photo} aspect="4 / 3" className="relative" />
    </div>
  );
}
