# Documentation visuals

[Documentation](../README.md)

## Screenshots

The `screenshots/` directory contains real application captures, not mockups:

- `web-today.png`, `web-analysis.png`, `web-journey.png`, `web-mobile.png`: English web interface, generated against a temporary SQLite database with synthetic entries and an account named `demo-reader`.
- `admin.png`: English administration interface, captured with synthetic accounts and a local simulated SMTP delivery service.
- `android-today.png`, `android-analysis.png`: native Android interface in French, captured on an emulator using the same synthetic demonstration account. They illustrate the native dashboard and analysis, not the mobile web interface.

No API tokens, passwords or private deployment URLs are shown. Capture only demonstration accounts and avoid settings screens that expose credentials. Screenshots describe the captured source state and may need refreshing after UI changes.

## Diagrams

Each diagram has an editable, standalone HTML source and an SVG for direct Markdown rendering. Both files must be updated together. HTML uses system fallbacks when remote fonts are unavailable; SVG exports use local fonts for portable embedding.

| Diagram | Source | Embedded image |
|---|---|---|
| Invitation and activation | [HTML](diagrams/account-invitation.html) | [SVG](diagrams/account-invitation.svg) |
| Application components | [HTML](diagrams/architecture.html) | [SVG](diagrams/architecture.svg) |
| Account synchronization | [HTML](diagrams/push-sync.html) | [SVG](diagrams/push-sync.svg) |
| Craving outcomes | [HTML](diagrams/coaching.html) | [SVG](diagrams/coaching.svg) |
| SQLite to PostgreSQL migration | [HTML](diagrams/postgresql-migration.html) | [SVG](diagrams/postgresql-migration.svg) |
| Kubernetes example | [HTML](diagrams/kubernetes.html) | [SVG](diagrams/kubernetes.svg) |
| iPhone shortcut actions | [HTML](diagrams/iphone-shortcut.html) | [SVG](diagrams/iphone-shortcut.svg) |

The iPhone figure is a configuration schematic based on the SuuLess API and Apple's Shortcuts documentation, not a device screenshot. It contains placeholder credentials only. The shortcut has not yet been validated on an iPhone; future device captures should use a synthetic account and hide the API key.

Diagrams are maintained with `diagram-design`. The Kubernetes diagram describes the public example resources; it contains no private installation topology. Keep diagrams concise, provide descriptive alternative text in guides, and verify that labels fit after edits.
