# RecoverAI — Design System

Give this file to Antigravity before any UI work (Phase 12 and any earlier UI touchpoints). The goal: a dense, trustworthy fintech operations console — closer to a real Razorpay/payments-ops product than a generic AI-demo UI. Not a chatbot. Not a template SaaS dashboard.

## Reference points
- Razorpay's own merchant dashboard: left sidebar nav, big number cards, a donut chart for method split, tabbed transaction tables below.
- Real ops consoles (fraud/risk platforms): dense KPI ticker row across the top, multiple small panels rather than one giant chart, live-status indicators, muted palette with sparing use of color for status (green/amber/red).

## Design tokens

**Color palette** (name 4–6 hex values, use consistently — don't drift):
- Background: near-white, slightly cool — `#F7F8FA`
- Surface/card: pure white `#FFFFFF` with a hairline border `#E4E7EC`, not heavy shadows
- Primary text: near-black `#101828`
- Secondary text: `#667085`
- Accent (used sparingly — primary actions, active nav, links): a deep indigo/blue, e.g. `#3538CD` — NOT Razorpay's exact brand blue (avoid implying official affiliation), but in the same trustworthy-fintech register
- Status colors: success `#12B76A`, warning `#F79009`, danger `#F04438` — used only for status dots, badges, and small indicators, never as large color blocks

**Typography:**
- A clean, functional sans-serif throughout — Inter or similar system sans. This is a data-dense operational tool, not a marketing page; do not use a decorative display face.
- Numbers (KPI figures) get a slightly heavier weight and tabular-nums so columns of numbers align.
- Clear type scale: large bold figures for KPI cards (~28–32px), section headers (~16px semibold), body/table text (~14px regular), captions/labels (~12px, secondary color).

**Layout:**
- Fixed left sidebar (nav: Overview, Transactions, Recovery Queue, Agent Replay, Policy Center, Experiment Lab), collapsible on narrow viewports.
- Top bar: product name + a persistent "Simulation / Test Mode" badge (this is required, not optional — see Ground Truth non-negotiable rules) + a system-status indicator.
- Content area: KPI card row at the top of every relevant screen, then panels/tables below in a grid — not one long scrolling column of unrelated content.
- Generous but not excessive whitespace; this should feel dense-but-organized, not cramped, not sparse.

**Signature element:** the Decision Receipt component (see Ground Truth / blueprint) is the one place to spend visual craft — a clean bordered card with a clear visual separation between "AI recommendation" and "Policy check" and "Final decision," so the recommend-vs-authorize distinction is visible at a glance without reading text. This is the single most important UI moment in the product — treat it accordingly, keep everything else quiet by comparison.

**Motion:** minimal and functional only — a live progress bar during batch runs, a subtle transition when a policy check resolves. No decorative animation. Restraint here reads as more professional, not less impressive.

## Copy guidelines
- Label things by what a merchant/ops user recognizes: "Recovery Queue," not "Escalation Buffer Service."
- Status/action language is active and specific: "Approved," "Blocked," "Escalated" — not vague states like "Processing" without a next step shown.
- Never claim real money was recovered — always "simulated."
- Failure/empty states explain what happened and what to do next, in the product's voice, not an apologetic tone.

## What to avoid
- No chatbot-style landing screen or conversational "Hi! I'm RecoverAI" copy.
- No heavy card shadows, no gradient backgrounds, no rounded-pill everything — keep it closer to hairline borders and flat surfaces, consistent with real fintech ops tools.
- No decorative icons without function — every icon should communicate a real status or action, not fill space.
- Don't reuse Anthropic's own default orange/cream AI-generated-look palette, and don't reuse Razorpay's literal brand blue — pick the indigo above and stay consistent.

## Responsiveness
Should be usable narrower (tablet width) even though the target use case is desktop — sidebar can collapse to icons, KPI cards can wrap to 2 columns instead of 4. Don't build a mobile app; a responsive web app is enough per the blueprint.
