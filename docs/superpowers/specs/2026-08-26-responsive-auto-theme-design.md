# Responsive Automatic Theme Design

## Goal

Extend the existing light and dark theme control with an automatic mode. The
automatic mode is the default and follows the operating system color-scheme
preference in real time. Desktop users receive a three-segment control, while
mobile users retain a compact cycling icon button.

## Scope

This change affects the shared public and administrative page shell, its theme
initialization script, the global interaction script, global theme-control
styles, and focused UI tests. Existing light and dark color tokens and page
layouts remain unchanged.

## Theme State

The user-facing preference has three values:

- `auto`: resolve the rendered theme from `prefers-color-scheme` and update it
  whenever that media query changes;
- `light`: always render the light theme;
- `dark`: always render the dark theme.

`localStorage.theme` stores the preference as `auto`, `light`, or `dark`.
Missing and unrecognized values resolve to `auto`, making automatic mode the
default and handling stale browser data defensively.

The root element exposes two separate attributes:

- `data-theme-mode="auto|light|dark"` records the user's preference;
- `data-theme="light|dark"` and `data-bs-theme="light|dark"` record the
  currently rendered theme used by existing CSS and Bootstrap.

Keeping preference separate from rendered appearance allows automatic mode to
change with the operating system without changing existing theme selectors.

## Initialization And Synchronization

The inline script in the document head reads and validates the saved mode,
resolves the rendered theme, and sets all root attributes before styles render.
This preserves the existing no-flash behavior.

The global site script owns subsequent changes. It provides one state update
path used by both responsive controls. A `prefers-color-scheme: dark` listener
updates the rendered theme only while the selected mode is `auto`. Explicit
light or dark modes ignore operating system changes.

Choosing any of the three modes writes that value to `localStorage.theme`.
Because `auto` is stored explicitly after selection, a user can return to it
after previously choosing a fixed theme.

## Responsive Controls

At widths of 769px and above, the navigation displays a segmented control with
three text options: `自动`, `白天`, and `夜间`. Each option is a button. The
active option exposes a visible selected state and `aria-pressed="true"`; the
other options expose `aria-pressed="false"`.

At widths of 768px and below, the navigation displays one compact icon button.
Each click advances in this order: `auto`, `light`, `dark`, then back to
`auto`. Its icon reflects the current preference, and its accessible label
states the current mode and the result of the next click. Stable button
dimensions prevent layout movement when the icon changes.

CSS media queries show exactly one control form at a time. Both forms remain in
the shared template and use the same JavaScript state, so resizing the viewport
does not change or lose the selected mode.

## Failure Handling

If browser storage is empty or contains an unsupported value, the application
uses automatic mode. Theme changes still apply in memory if writing to browser
storage is unavailable. The initialization and interaction scripts use the
same validation and resolution rules to prevent disagreement between the first
paint and the interactive state.

## Testing

Focused tests will verify that:

- the shared shell contains the desktop segmented control and mobile cycling
  button with accessible state hooks;
- the initialization script defaults missing and invalid values to `auto` and
  separates preference from the rendered light or dark theme;
- the interaction script supports direct desktop selection and the required
  mobile cycle order;
- automatic mode reacts to system theme changes while fixed modes do not;
- all three choices are persisted and both controls stay synchronized;
- responsive CSS swaps control forms at the existing 768px breakpoint and
  preserves stable mobile-button dimensions.

The complete UI test suite will be run after implementation. Manual browser
checks will cover desktop and mobile widths in automatic, light, and dark modes,
including a live operating system theme change while automatic mode is active.

## Out Of Scope

- New color palettes or changes to existing light and dark tokens.
- Server-side or account-level theme preferences.
- Per-page theme controls.
- A dropdown theme menu.
