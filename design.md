# design.md — Pacify design language

Source: Pacifyco Brand Guide v1.0 (October 2026). Read this before any UI or copy work.
Principle from the guide: don't design something that explains Pacify — design something that makes
people *feel* Pacify.

---

## 1. Brand in one minute

- **Promise:** "A little help for you. A little more fun for them." Every experience serves both halves:
  time and relief for the parent, care and play for the child.
- **Story:** from "I can't always be there." (guilt, overload) → "I don't have to do it all."
  (permission) → trust and freedom with Pacify.
- **Positioning:** not "a platform to find babysitters". A trusted helping hand. Avoid marketplace
  language: no "book in minutes", "thousands of sitters", "lowest rates".
- **Audience:** urban Indian parents, 28–42, often both working, digitally fluent, allergic to cutesy or
  salesy design. Secondary: sitters — skilled partners, never "inventory".
- **Personality:** warm not saccharine, human not clinical, trustworthy not corporate, modern not trendy,
  calm not sleepy, subtly playful not childish.

### Trust pillars (every sitter-facing journey answers these, in this order)

1. Who is looking after my child? — real name, face and a short story.
2. Are they verified? — the checks we actually do, stated plainly.
3. What experience do they have? — years, age groups, families served, first aid.
4. Can I meet them first? — yes, always: a free introduction before the first booking.
5. Additional safety — reserved for Pacify Plus, **not in v1** (see section 11).

---

## 2. Voice and copy

- Understand before you offer; give permission, not guilt; be specific about safety (facts, not
  adjectives); keep it light, never at the child's or parent's expense.
- **Sentence case** for headings, buttons and navigation. Only eyebrows and the tagline lockup are
  uppercase.
- **Full stops** on headline statements; never on buttons, labels or nav.
- **The arrow →** only on the single primary forward action.
- **No exclamation marks, no emoji, no urgency, no guilt, no superlatives.**
- British/Indian spelling (colour, neighbourhood, organise). No Oxford comma.
- Numerals: 6 years, 6:30 pm, 12 Oct 2026, ₹250/hour.
- In copy the brand is **Pacify**; the wordmark reads **pacifyco**.

| Use | Avoid |
| --- | --- |
| sitter, care, helping hand | babysitter (in headlines), nanny, maid, worker |
| little one, your child | kids, brats, munchkins |
| breathing room, time for you | me-time hacks, escape |
| verified, met, checked | vetted, 100% safe |
| flexible, fair | cheap, discount |
| join, try, meet | buy now, hurry, limited |

### Tone by moment

| Moment | Tone | Example |
| --- | --- | --- |
| Empty states, onboarding | Empathetic, quiet | Some days, there just aren't enough of you to go around. |
| Trust / verification | Plain, factual, warm | Meet your sitter first. It's free, and it's how every Pacify booking begins. |
| Errors | Helpful, blame-free | That email doesn't look quite right — could you check it? |
| Sitter recruitment | Respectful, proud | Care is skilled work. We pay and treat it that way. |
| Calls to action | Inviting, low-pressure | Meet your sitter · See how it works · Become a sitter |

Never use "Book now". For booking actions use e.g. "Choose a time" or "Confirm this time".
Emails: 600px single column on Blush with a white card, one primary button, signed
"Warmly, the Pacify team".

---

## 3. Colour

Always use the variables, never raw hex in components. Rough proportion: 70% blush and white, 20%
chocolate, 10% coral. If a screen feels loud, remove coral first.

Base palette: Chocolate `#2D221D`, Coral `#F5695A`, Peach `#FDC7AC`, Blush `#FFF1E8`, Cream/white
`#FFFFFF`.

### Semantic variables (light / dark)

```css
:root {
  --surface-default: #FFF1E8;   /* page ground */
  --surface-raised:  #FFFFFF;   /* cards, nav, inputs */
  --surface-sunken:  #FBE6D9;   /* alternating sections, quiet panels */
  --surface-tint:    #FDC7AC;   /* icon discs, avatars; ink text only */
  --surface-inverse: #2D221D;   /* footer, dark bands */
  --accent-coral:    #F5695A;   /* the mark, primary button fill, underlines */
  --text-ink:        #2D221D;   /* all headlines and body */
  --text-muted:      #6E5A50;   /* captions, meta; not on surface-tint */
  --text-on-coral:   #2D221D;   /* labels on coral fills; never white */
  --text-coral-display: #F45544;/* coral headlines 24px+ only */
  --text-coral-deep: #C2412F;   /* coral at text size: links, prices, icons on tint */
  --border-line:     #EBD9CC;   /* decorative hairlines */
  --border-strong:   #9C7F70;   /* input and control borders */
  --border-focus:    #2D221D;   /* 2px focus outline, 3px offset */
  --status-trust:    #2E6B57;   /* verified ticks and labels only, always with words */
  --status-danger:   #9E2A2B;   /* form errors, always with icon and message */
}

[data-theme="dark"] {
  --surface-default: #2D221D;
  --surface-raised:  #3A2D27;
  --surface-sunken:  #241B17;
  --surface-tint:    #4A352C;
  --surface-inverse: #FFF1E8;
  --accent-coral:    #F5695A;
  --text-ink:        #FFF1E8;
  --text-muted:      #C9B4A8;
  --text-on-coral:   #2D221D;
  --text-coral-display: #F5695A;
  --text-coral-deep: #FF8A7A;
  --border-line:     #4A3A32;
  --border-strong:   #A08779;
  --border-focus:    #FFF1E8;
  --status-trust:    #8CCFB6;
  --status-danger:   #FFB3A7;
}
```

Follow the OS setting by default (`prefers-color-scheme`), with a manual toggle.

### Accessibility rules

- Small text needs 4.5:1; text 24px+ and meaningful icons need 3:1.
- **Never white text on coral** (fails at 2.98:1). Labels on coral are chocolate.
- Coral at text size is always `--text-coral-deep`; `--text-coral-display` only at 24px+.
- Status colours always come with words (and an icon for errors).

---

## 4. Typography

- **Poppins** (Google Fonts) for everything. Weights: Light 300 (captions), Regular 400 (body),
  Medium 500 (nav, buttons, labels), SemiBold 600 (section headings), Bold 700 (hero headlines).
- **Caveat** for handwritten asides only: at most one per screen, six words max, never on buttons,
  prices or trust information.
- Fallbacks: `"Helvetica Neue", Arial, sans-serif` for Poppins; `"Segoe Print", cursive` for Caveat.

| Style | Size / line height | Weight | Tracking |
| --- | --- | --- | --- |
| Display XL | 72 / 76 | Bold | −1.5px |
| Display | 56 / 60 | Bold | −1px |
| H1 | 44 / 52 | SemiBold | −0.75px |
| H2 | 32 / 40 | SemiBold | −0.5px |
| H3 | 24 / 32 | SemiBold | −0.25px |
| Body LG | 18 / 30 | Regular | 0 |
| Body | 16 / 26 | Regular | 0 |
| UI | 15 / 22 | Medium | 0 |
| Small | 14 / 22 | Regular | 0 |
| Caption | 12 / 18 | Light | 0 |
| Eyebrow | 12 / 16 | Medium, uppercase | +4px |
| Script | Caveat 30 / 34 | Bold | 0 |

Scale display sizes down on phones (Display XL and Display are for marketing pages; app screens
usually top out at H1). Max line length 32ch for display, 62ch for body. Left-align by default. One
display line per screen.

---

## 5. Layout, spacing, shape and depth

Spacing scale: `space-1` 4px, `space-2` 8px, `space-3` 12px, `space-4` 16px (phone side margin),
`space-5` 24px (compact card padding, gutter), `space-6` 32px (roomy card padding), `space-7` 48px,
`space-8` 64px, `space-9` 96px, `space-10` 128px, `space-11` 160px.

Radius: `radius-sm` 8px (tags, checkboxes), `radius-md` 16px (inner panels, menus), `radius-lg` 24px
(cards, photos, nav), `radius-xl` 32px (large panels, bands), `radius-pill` 999px (**every** button,
input and chip).

Shadows: `shadow-soft` `0 8px 24px rgba(45,34,29,.08)` (resting cards, nav);
`shadow-lift` `0 18px 48px rgba(45,34,29,.14)` (hover, floating).

Grid: 12 columns, 1200px max content, 24px gutters on desktop; 4 columns and 16px margins on phones.
Design mobile-first; the app must work at 360px width and 200% zoom.

Focus: 2px `--border-focus` outline with 3px offset on every interactive element.

Generous whitespace is part of the calm: when in doubt, add space, not elements.

---

## 6. Logo

- Lowercase rounded **pacifyco** wordmark in Chocolate; the final "o" is a coral pacifier ring with a
  peach handle. Reversed version uses Blush lettering on Chocolate (dark theme).
- **Use the supplied SVG files only. Never retype the wordmark in Poppins**, recolour, stretch, rotate,
  add effects, or place the primary version on coral or peach.
- The symbol alone is used for the favicon, app icon (symbol at ~62% of a rounded square, radius ~22%),
  avatar and loading states.
- Clear space = the height of the symbol's ring on every side. Minimum: wordmark 96px, symbol 20px.
  In navigation: 28px tall on desktop, 24px on mobile.
- Until the SVGs are in `/web/src/assets/brand/`, use a plain text placeholder marked `TODO: logo`.

---

## 7. Iconography

Rounded line icons, 24px grid, 1.75px stroke, round caps and joins, no fills. Use Lucide with
`strokeWidth={1.75}` until the final drawn set exists. Sizes: 20–22px inline in ink; 28px on a 64px
peach disc in `--text-coral-deep`. `--status-trust` only for verification ticks. **Every icon has a
visible text label** — no icon-only controls except the close button (which still has an aria-label).

---

## 8. Photography

Warm natural light, lived-in Indian homes, real Indian parents (mostly 30s) showing relief, focus,
ease and connection; sitters as warm professionals at the child's eye level. Children's faces only
with documented consent. Avoid: crying children, guilty or frazzled parents, cartoon babies, pastel
nursery clichés, Western stock photos. Type on photos: headline only, top-left, blush text over a
chocolate scrim, 24×2px coral underline — never body copy, prices or trust information on a photo.
Final photography isn't commissioned yet. Until it is, the app uses seven interim photos Reuben chose
from `/assets` (children's faces covered), served from `web/src/assets/photos/` through the `Photo`
component: a decorative image (empty alt text), rounded, fading in on the calm curve. Swapping in the
commissioned photos means replacing those files.

---

## 9. Motion

Calm, never bouncy. Easing `cubic-bezier(.22, 1, .36, 1)`. Durations: 200ms UI, 600ms text reveals,
900ms image transitions. Rise 16–24px; never slide in from off-screen. Stagger 80–120ms. Never bounce,
spring overshoot, spin, fast parallax or autoplaying video with sound. Respect
`prefers-reduced-motion` everywhere.

---

## 10. Components (build these first, in `/web/src/components/ui`)

- **Button** — pill. Primary: coral fill, chocolate label, arrow only when it's the primary forward
  action. Secondary: outline with `--border-strong`. Tertiary: text link in `--text-coral-deep`.
  Full-width on phones for the primary action.
- **Input / Select / Textarea** — pill (textarea `radius-md`), white surface, `--border-strong`, label
  above, error below with icon and blame-free message in `--status-danger`.
- **Chip / Tag** — pill, peach or sunken surface, ink text (e.g. "Ages 1–8", "Storytime").
- **VerifiedChip** — trust-green tick plus words, e.g. "ID & police verified", "First-aid certified".
- **Card** — white, `radius-lg`, `shadow-soft`, `space-5`/`space-6` padding.
- **SitterCard** — photo or initials avatar on peach, name, years of experience and area (caption),
  chips for age groups and interests, VerifiedChips, rating and "Trusted by N Pacify families", primary
  action "Meet [first name] first" (or "Choose a time" for unlocked pairs). **No price on the card** —
  parents don't see sitter rates.
- **BookingCard** — "Next booking" eyebrow, date and time ("Sat, 11 Oct · 10:00 am – 1:00 pm"), "[Sitter]
  is looking after [child] at home."
- **HourBalance** — child-hours remaining per child, nearest expiry, carried-forward hours.
- **IconTile** — 28px icon on 64px peach disc with label.
- **RoleChooser** — "I'm a parent" / "I'm a sitter".
- **EmergencyButton** — always visible on active bookings; chocolate surface with clear label
  "Emergency or report"; confirmation step to avoid accidental taps. (Not coral: coral is for primary
  actions.)
- **Empty states** — one empathetic line, one helpful action.
- App home greeting pattern: "Time for you, [first name]." with the next booking card below.

---

## 11. Where the brand guide and the v1 product differ (follow this file)

1. **Pacify Plus** (enhanced checks, live check-ins, support line) isn't in v1. Don't show the badge or
   the fifth trust pillar.
2. **Address verification** is mentioned in the guide, but v1 checks are ID, police verification,
   references, a psychology test and interviews. Only claim those.
3. **Sitter card price** — the guide shows "₹450/hour · 1 child"; v1 parents pay pack rates and never
   see a sitter's rate. Show no hourly price on sitter cards.
4. **"Join the waitlist"** belongs to the marketing site (scrollytelling, phase 13). In the app the
   primary actions are signing up, meeting a sitter and choosing a time.
