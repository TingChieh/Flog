# Friendly Links Card Grid Design

Date: 2026-08-25
Status: Approved for implementation planning

## Goal

Restore the public Friendly Links page to a card-based layout inspired by the
previous three-column design, while fixing inconsistent alignment caused by
different title and description lengths.

## Scope

This change affects only the public Friendly Links page. It does not change link
records, avatars, URLs, administration screens, permissions, or editing flows.
The existing page heading, empty state, light theme, and dark theme remain.

## Structure

Replace the shared horizontal `data-list` and `functional-row` presentation in
`links.html` with link-specific semantic classes:

- The list is a responsive CSS grid.
- Each list item is one link card.
- Each card contains a header row, description, and action area.
- The header row contains the existing 40-pixel avatar and link name.
- The action continues to open the destination in a new tab and includes
  `rel="noopener noreferrer"`.

The link name remains visible next to the avatar, so the avatar uses an empty
alternative description to avoid repetitive screen-reader output.

## Responsive Layout

The grid uses three explicit responsive states:

- Wide desktop: three equal-width columns.
- Intermediate widths: two equal-width columns so cards do not become cramped.
- Mobile: one full-width column.

The existing 1080-pixel content width remains authoritative. Breakpoints should
fit the current stylesheet's responsive structure and preserve at least the
existing 44-pixel mobile action target.

## Alignment

CSS Grid stretches cards to the height of the tallest card in each row. Each
card is also a vertical flex container:

- Avatar and title share one centered baseline area.
- Long names and descriptions wrap without forcing horizontal overflow.
- The description occupies the flexible middle area.
- The action area uses automatic top margin, placing every Visit Website button
  on the same bottom edge within its row.

Card padding, borders, corner radius, and typography use the existing design
tokens. The result remains restrained and consistent with the current
monochrome editorial theme rather than reproducing Bootstrap's legacy card
styling.

## Empty And Edge States

When no links exist, the current empty-state message remains unchanged. Long
unbroken names or descriptions wrap inside their card. A final incomplete row
aligns to the grid's left edge and does not stretch cards across missing
columns.

## Testing

Add focused UI tests that verify:

- The public links page renders the new grid and card classes.
- The old shared horizontal row classes are absent from link cards.
- External link actions retain a new-tab target and add safe `rel` values.
- The stylesheet defines three-, two-, and one-column states.
- Card CSS uses grid stretching and vertical flex behavior to align actions.

Run the focused UI tests, then the broader page and shell test suites. Verify
the rendered page at desktop and mobile widths to confirm wrapping, equal row
heights, bottom-aligned actions, and absence of horizontal overflow.
