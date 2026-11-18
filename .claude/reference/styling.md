# Styling and page layout

*Read this before changing any CSS, template markup or page layout.*

## Styling: shared components, never page-local patches

**Style with reusable components in `_static/global/css/`. A page template
composes existing classes; it does not carry its own tweaks.** No inline
`style=`, no one-off rule added to make a single page look right, no
page-specific override of a shared component.

This is the collapsed-distinction rule wearing a stylesheet. Every CSS bug in
this template came from the same shape:

- `.welcome-card` was referenced by three templates and **defined nowhere** — it
  came from a snapshot without its rule, so those pages simply had no centring.
- The instructions page carried **two widths for one concept** (a band *and* a
  reading measure), so the text, the eyebrow and the pager each landed on a
  different number and the pager could not be aligned.
- `logo_section.html` set `height` **inline**, which beats any stylesheet, so
  the component's own rule was inert until the attribute was removed.

**When a page needs something new:** add a component, give it an INTENTION
comment saying what it is for, and add a specimen to
`_static/global/html/template.html` so it is demonstrated rather than orphaned.
When two pages need the same thing, they use the **same class** — the same
component obeying different rules in different places is a defect even when each
instance looks reasonable on its own.

**Genuine exceptions exist** (a page-level rule that truly belongs to one
screen). Mark them `EXCEPTION` with the reason, so the next reader can tell a
deliberate departure from an accreted patch.

**A change here also ages the website.** The screens on the academic site are
built from these stylesheets by `scripts/site_previews/build_site_previews.py` (checked by
`scripts/site_previews/check_site_previews.py`); re-run both after touching
`_static/global/css/` — **and after touching `core/experimenter_dashboard.py`'s own
stylesheet or its `renderRow`**, which the monitor preview is literally rendered
by. Nothing fails if you don't — the site simply goes on showing an older study,
which is exactly how the hand-written snapshots it replaced went stale.

## Template HTML Layout
The file [`_static/global/html/template.html`](../../_static/global/html/template.html) serves as the core visual template for most experimental pages. It is located in the `_static/global/html/` directory of your project. This template demonstrates and defines how all of the pre-defined CSS sections will look and behave, providing a live preview of your main screen layout.

- **Header Section**: Shows how the experimental screen header appears, including the title and subtitle, styled using the shared CSS (`_static/global/css/base.css` and the per-page files beside it, linked together by `_static/global/html/css_bundle.html`).
- **Main Content Area**: Contains a section for page headings and standard paragraph text, both vertically and horizontally centered within a card. This section uses classes such as `.experimental-content`, `.section-title`, and `.section-text` to illustrate their styling.
- **Navigation Buttons**: Displays the "Back" and "Next" buttons with their associated styles (`.button-row`, `.next-button`).
- **Logos Section**: Includes a common logos area displayed at the bottom of the intro and outro screens.

By editing or viewing this file in your browser, you can see how the different visual building blocks (as defined in the referenced CSS) are applied. When creating new pages, structure your content to fit inside this card layout by extending or including this template, ensuring consistency across experimental screens.
