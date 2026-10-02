---
name: SBI Mutual Fund Assistant Design System
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#424654'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#737785'
  outline-variant: '#c3c6d6'
  surface-tint: '#0056d2'
  primary: '#0040a1'
  on-primary: '#ffffff'
  primary-container: '#0056d2'
  on-primary-container: '#ccd8ff'
  inverse-primary: '#b2c5ff'
  secondary: '#006c4f'
  on-secondary: '#ffffff'
  secondary-container: '#59fdc5'
  on-secondary-container: '#007354'
  tertiary: '#663f00'
  on-tertiary: '#ffffff'
  tertiary-container: '#865400'
  on-tertiary-container: '#ffd29e'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dae2ff'
  primary-fixed-dim: '#b2c5ff'
  on-primary-fixed: '#001847'
  on-primary-fixed-variant: '#0040a1'
  secondary-fixed: '#59fdc5'
  secondary-fixed-dim: '#2fe0aa'
  on-secondary-fixed: '#002116'
  on-secondary-fixed-variant: '#00513b'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  display-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  display-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 26px
    fontWeight: '700'
    lineHeight: 34px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  label-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
  timestamp:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 14px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.25rem
  gutter-mobile: 0.75rem
  margin: 1.5rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style
This design system defines a high-trust, modern conversational fintech interface balancing the institutional credibility of SBI Mutual Fund with the clean, energetic, and accessible clarity of modern wealth-tech platforms like Groww.

### Personality & Tone
- **Authoritative yet Approachable:** Factual, crisp, and objective. It removes financial jargon and unnecessary clutter, instilling confidence through transparency.
- **Disciplined & Compliant:** Visual guardrails clearly distinguish informational answers from investment advice, ensuring regulatory trust.
- **Effortless Clarity:** Generous white space, fine-lined borders, and deliberate contrast create an atmosphere of safety, order, and precision.

### Design Movement
The style blends **Modern Minimalist Fintech** with **Structured Conversational UI**:
- Ultra-clean canvas surfaces (`#F8FAFC` to `#FFFFFF`) paired with razor-thin slate borders (`#E2E8F0`).
- Deep institutional SBI Blue paired with Groww-inspired emerald teal as an action color.
- Soft, pill-rounded badges and generous `rounded-2xl` component enclosures that convey a welcoming, state-of-the-art digital assistant.

## Colors
The color architecture prioritizes institutional trust, immediate legibility, and unmistakable feedback states.

### Palette Roles
- **Primary (`#0056D2` - SBI Blue):** Anchor color used for brand identifiers, selected navigation, primary assistant iconography, and active scheme badges.
- **Secondary (`#00D09C` - Groww Emerald):** Kinetic accent for affirmative states, input submit triggers, success badges, and primary action affordances.
- **Tertiary (`#F59E0B` - Amber Guardrail):** Dedicated warning accent for regulatory constraints, disclaimers, and advice guardrails ("Facts-only. No investment advice").
- **Neutral Primary (`#0F172A` - Slate 900):** High-contrast text color ensuring maximum legibility on light cards.

### Functional Surfaces & Semantic Fills
- **App Canvas:** `#F8FAFC` (Slate 50) creates subtle separation behind pure white content cards.
- **User Bubble Fill:** `#EEF2F6` with border `#E2E8F0` and `#1E293B` text.
- **Assistant Container:** Pure `#FFFFFF` surface enclosed by a `#E2E8F0` hairline border with a light elevation.
- **Guardrail Surface:** Amber tinted fill (`#FFFBEB`) with border `#FDE68A` and icon/title in `#D97706`.
- **Informational / Missing Data Surface:** Neutral tinted fill (`#F8FAFC`) with border `#E2E8F0` and icon/title in `#475569`.

## Typography
The system pairs **Plus Jakarta Sans** for headlines and brand titles with **Inter** for all conversational and transactional body layers.

- **Plus Jakarta Sans:** Selected for its friendly, rounded geometry and modern corporate clarity. Used strictly for assistant introductions, scheme titles, and hero headings.
- **Inter:** Chosen for body reading comfort, strict numerical legibility (TER, NAV figures, percentages), metadata timestamps, and disclaimers.
- **Typographic Hierarchy:** Keep prompt questions concise in semi-bold weight (`headline-sm`). Conversational responses stay at `body-md` (14px/22px) to optimize scanning speed on both desktop and mobile screens.

## Layout & Spacing
The layout implements a centralized, focused conversational column surrounded by clean atmospheric whitespace.

### Grid & Composition
- **Chat Max Width:** The active thread container centers inside a maximum column width of `768px` on desktop and expands edge-to-edge on mobile with safe gutters.
- **Vertical Flow:** Standard gap of `space-lg` (20px) between alternating user and assistant exchanges.
- **Message Internal Density:** Assistant reply cards employ `space-lg` internal padding to comfortably house title headers, body text, and source attribution footers.
- **Input Bar Dock:** Fixed or floating bottom docked bar at `space-lg` elevation from viewport bottom, containing unified text field and action trigger.

## Elevation & Depth
Depth in this system is subtle and functional, relying on delicate borders and ambient diffuse shadows rather than dense drop shadows.

- **Flat Baseline:** The app backdrop (`#F8FAFC`) hosts pure white (`#FFFFFF`) cards outlined by a hairline `1px solid #E2E8F0` border.
- **Ambient Card Elevation:** Interactive scheme cards, assistant bubbles, and the docked input container utilize an ultra-soft shadow: `0px 1px 3px rgba(15, 23, 42, 0.04), 0px 4px 12px rgba(15, 23, 42, 0.03)`.
- **Floating Input Field:** The persistent search/input tray uses a slightly lifted elevation: `0px 4px 20px rgba(0, 86, 210, 0.06), 0px 1px 4px rgba(15, 23, 42, 0.05)`.
- **No Heavy Outlines:** Avoid thick borders; all structural separation relies on 1px stroke weight using `#E2E8F0` or status-tinted borders.

## Shapes
The system relies on generous, soft contours that maintain structured fintech rigor.

- **Cards & Chat Containers:** Standardized on `rounded-2xl` (16px / 1rem) for assistant cards, suggestion panels, and prompt bubbles.
- **Pill Badges & Buttons:** `rounded-full` (9999px) applied to topic suggestion chips, regulatory status banners ("Facts-only. No investment advice"), category tags, and the circular send button.
- **Interactive Form Inputs:** Rounded container of `rounded-full` or `rounded-2xl` matching modern search surfaces like Groww.

## Components

### Chat Message Bubbles
- **User Prompt:** Right-aligned bubble with background `#EEF2F6`, border `1px solid #E2E8F0`, `rounded-2xl` shape with a slightly reduced bottom-right radius (`rounded-br-sm`), typography `body-md` in `#1E293B`. Accompany with user avatar or neutral icon.
- **Assistant Card:** Left-aligned, pure `#FFFFFF` background, border `1px solid #E2E8F0`, `rounded-2xl` padding of `1.25rem`. Prefaced by the circular assistant emblem (SBI gradient blue circle). Contains scheme title, structured response, and metadata footer.
- **Typing / Loading State:** Left-aligned `#F8FAFC` card with animated pulsating emerald/blue dots and secondary status text ("Searching relevant information from SBI Mutual Fund sources...").

### Specialized Message States
- **Guardrail Card (Advice / PII / Disclaimers):**
  - Background: `#FFFBEB`
  - Border: `1px solid #FDE68A`
  - Icon: Amber exclamation triangle (`#D97706`)
  - Title: Bold `14px` in `#B45309` ("I can't provide investment advice.")
  - Body: Neutral `14px` explaining available factual details.
- **Not Found / Fallback Card:**
  - Background: `#F8FAFC`
  - Border: `1px solid #E2E8F0`
  - Icon: Slate search lens (`#64748B`)
  - Content: Helpful prompt suggesting supported topics (expense ratios, exit load, lock-in period).

### Source Link Footer
- Appears docked at the bottom of assistant cards separated by a hairline divider or subtle spacing.
- Includes link icon (`#0056D2`), source anchor label ("Source: SBI Mutual Fund" or "Source: Groww"), external link glyph (`↗`), and verified sync date (`11px` Slate 500).

### Prompt Suggestion Cards (Welcome Screen)
- 3-column desktop / 1-column mobile grid of cards.
- Background `#FFFFFF`, border `1px solid #E2E8F0`, rounded `16px`, padding `1rem`.
- Features an icon enclosed in a soft blue/emerald squircle container, two-line prompt question, and trailing chevron (`>`).

### Topic Filter Chips
- Capsule-style `rounded-full` pills.
- Border `1px solid #E2E8F0`, background `#FFFFFF`, text `#0056D2` or `#475569`.
- Hover state: Background `#F1F5F9`, border `#CBD5E1`.

### Unified Query Input Dock
- Enclosing container: Full-width within chat column, background `#FFFFFF`, border `1px solid #E2E8F0`, pill-shaped `rounded-full`, inner padding `0.375rem 0.5rem 0.375rem 1.25rem`.
- Leading icon: Subtle slate search or prompt glyph (`#94A3B8`).
- Input: Borderless text input with placeholder `"Ask a question about SBI Mutual Fund..."`.
- Submit Button: Circular `40px` pill in Emerald `#00D09C` (or `#0056D2` on hover) with crisp white directional arrow icon (`→`).