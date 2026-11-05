# Aisaka's Blog Apple Editorial Redesign

## Goal

Redesign the full site around a restrained Apple editorial aesthetic while
preserving the existing central hero as the site's visual identity. The
redesign changes presentation and interaction only; routes, data models,
permissions, forms, comments, likes, search, and other application behavior
remain intact.

## Visual Direction

The site uses a monochrome Apple-inspired system built from white, near-black,
and neutral gray surfaces. Blue is reserved for links and focused interactive
states. Green is removed from navigation, buttons, badges, and general UI.

The current lake image, Aisaka logo, `Hello World!`, `你好世界`, and welcome
line remain in the homepage hero. Their composition may receive small spacing,
contrast, and responsive adjustments, but the image and central brand content
will not be substantially redesigned.

`SmileySans-Oblique` (得意黑) remains the brand voice for `Aisaka's Blog` and
the central hero copy. Navigation, article titles, body copy, metadata, forms,
and utility UI use the native system font stack for Apple-like clarity and
better long-form readability.

## Layout And Navigation

The top navigation becomes a compact monochrome bar with a restrained divider
or translucent blur where supported. Desktop navigation remains fully visible.
Mobile navigation uses the existing collapsible behavior with a simplified
menu icon, predictable spacing, and a full-width menu that does not overlap
page content.

Search, theme switching, authentication state, unread counts, and existing
navigation destinations remain available. Controls use familiar icons where
possible and include accessible names and focus states.

Content width is constrained consistently across pages. The homepage uses an
editorial single-column article list with an optional compact category rail at
wide breakpoints. Other pages reuse the same spacing, typography, form, list,
and action patterns instead of introducing separate visual systems.

## Homepage And Article Lists

The homepage keeps its existing central hero. Below it, content changes to an
Apple editorial list with generous but controlled whitespace and thin neutral
dividers.

Desktop article titles target approximately 24 to 28 pixels. Mobile article
titles target approximately 20 to 22 pixels. Metadata and excerpts stay
compact so more than one article can be scanned in a normal viewport.

There is no visible `Continue reading` link. The article title and its list
row provide the navigation target, with clear hover and keyboard focus states.
Copy, QR, edit, and delete remain available as quiet utility actions without
dominating the reading hierarchy.

## Article Detail And Comments

Article detail pages use a narrower reading measure, system-font body text,
clear heading levels, comfortable line height, and restrained metadata.
Existing article HTML remains unchanged and continues through the current
sanitization path.

Like, copy, edit, delete, comment submission, and comment deletion retain their
current behavior. Buttons are restyled into a consistent command hierarchy:
filled black for primary actions, neutral outline or text treatments for
secondary actions, and red only for destructive actions.

Comments use a simple divided list rather than decorative nested cards. Forms
use Apple-like fields with visible labels, clear validation states, and full
keyboard support.

## Supporting Pages

Movie, Todo, Links, About, categories, search results, profiles, messages,
authentication, edit screens, pagination, alerts, and empty states adopt the
same tokens and layout rules. Functional density is preserved for management
pages; they will not be turned into oversized marketing layouts.

Bootstrap remains available for grid and behavior compatibility, but custom
styles define the visible design. Legacy inline presentation, obsolete `font`
tags, and inconsistent one-off colors are removed where they affect the
redesign.

## Theme Behavior

The existing light/dark preference and theme toggle remain. Light mode uses
white and `#f5f5f7`-style surfaces; dark mode uses near-black and charcoal
surfaces without introducing a colored tint. Both themes retain readable
contrast, visible borders, and consistent hierarchy.

Theme initialization continues before first paint to prevent flashing. The
redesign respects `prefers-color-scheme` and `prefers-reduced-motion`.

## Footer And Back To Top

The footer remains on every page. It becomes a full-width light-gray or
dark-neutral band with a thin divider and compact content. It keeps:

- the Aisaka copyright line;
- `Powered by Flog`;
- the existing Login or Logout action;
- a short Aisaka's Blog descriptor.

On mobile, footer content stacks vertically. The year is generated dynamically
instead of remaining hard-coded.

A small circular up-arrow control is fixed at the bottom-right after the user
scrolls beyond one viewport. It smoothly returns to the top, never covers
footer links or primary actions, supports keyboard focus, and disables motion
when the operating system requests reduced motion.

## Component Boundaries

The redesign is implemented through shared tokens and reusable page-level
classes rather than per-template visual patches:

- global color, spacing, typography, radius, border, and motion tokens;
- shared navigation, hero, footer, back-to-top, button, form, list, alert,
  pagination, and empty-state rules;
- homepage and article-detail layouts;
- compact management-page variants where dense controls are necessary.

JavaScript remains limited to navigation expansion, theme switching,
back-to-top visibility and scrolling, plus existing application interactions.
No new frontend framework is introduced.

## Responsive And Accessibility Requirements

The redesign must work at 390 by 844 mobile, common tablet widths, 1440 by 900
desktop, and wide desktop. Text must not overlap controls or escape containers.
Navigation, fixed controls, alerts, and forms must remain usable at 200 percent
zoom.

All interactive elements need visible focus states, semantic labels, sufficient
contrast, and stable hit areas. Hover cannot be the only indicator. Layout and
content remain usable without animation.

## Error And Empty States

Existing Flask validation and flash behavior is preserved. Errors appear next
to their fields and use concise red accents without shifting unrelated layout.
Empty lists use quiet text in the normal content flow rather than decorative
cards. Disabled pagination and unavailable actions remain visibly distinct.

If the custom brand font fails, brand text falls back to the system font
without hiding content or changing control dimensions.

## Verification

Implementation verification includes:

- the existing Python test suite with `DATABASE_URL=sqlite://`;
- route smoke checks for the homepage, article detail, supporting public pages,
  login, and representative management pages;
- desktop and mobile screenshots of the homepage and article detail at the same
  viewports used for the saved pre-redesign baseline;
- visual checks for light and dark mode, open mobile navigation, long titles,
  form validation, comments, footer layout, and back-to-top behavior;
- console checks for frontend errors and missing static assets.

The preserved baseline is stored at
`instance/backups/ui-before-apple-2026-08-20.tar.gz`, with screenshots under
`instance/backups/ui-before-apple-2026-08-20/`.
