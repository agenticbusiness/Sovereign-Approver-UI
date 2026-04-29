# Sovereign Spec UI - Design System
> **Codename:** TITAN HULL
> **Aesthetic:** Stainless Steel Future Ship - Clean lines, clear compartments
> **Version:** 1.0.0

## Design Philosophy
The UI emulates the interior bridge of a futuristic stainless steel vessel. Every section is a distinct **compartment** with brushed-metal borders, recessed panels, and precise typographic hierarchy. Zero visual noise. Maximum information density.

## Color Palette

| Token | Hex | Usage |
|-------|-----|-------|
| `--hull-base` | `#0c0e12` | Primary background (deep void) |
| `--hull-panel` | `#14171e` | Recessed panel background |
| `--hull-elevated` | `#1c2029` | Elevated compartment surfaces |
| `--steel-border` | `#2a3040` | Primary compartment dividers |
| `--steel-bright` | `#3d4558` | Active/hovered borders |
| `--steel-rivet` | `#4a5570` | Accent dots, indicators |
| `--text-primary` | `#e8ecf2` | Primary readout text |
| `--text-secondary` | `#8893a7` | Secondary labels, metadata |
| `--text-muted` | `#4e5a72` | Disabled, tertiary content |
| `--signal-green` | `#00e68a` | Approved, success, active |
| `--signal-red` | `#ff4d6a` | Rejected, error, critical |
| `--signal-amber` | `#ffb84d` | Pending, warning, in-progress |
| `--signal-cyan` | `#00d4ff` | Info, links, interactive hover |
| `--glow-green` | `rgba(0, 230, 138, 0.08)` | Approved panel background |
| `--glow-red` | `rgba(255, 77, 106, 0.08)` | Rejected panel background |

## Typography
- **Primary Font:** `'Inter'`, system-ui, sans-serif
- **Monospace:** `'JetBrains Mono'`, monospace
- **Header Scale:** 1.125rem / 0.9rem / 0.8rem / 0.72rem
- **Body:** 0.82rem at 1.5 line-height
- **All Caps:** Used for compartment headers and status labels only

## Compartment System
Every UI section is a **compartment** with:
- 1px `--steel-border` outline
- 12px internal padding
- 4px border-radius (subtle machined edges)
- Recessed background (`--hull-panel`)
- Uppercase label header in `--text-secondary` at 0.65rem with 2px letter-spacing

## Layout (3-Column Bridge)
```
+--------------------+-----------------------------+------------------+
| NAV COMPARTMENT    | VIEWPORT (PDF Render)       | STATUS READOUT   |
| - Doc Selector     | - Full page image           | - Remaining: N   |
| - Page Nav         | - Bounding box overlays     | - Approved: M    |
| - Action Buttons   |                             | - Match List     |
|                    |                             | - Reject Notes   |
+--------------------+-----------------------------+------------------+
```

## Interaction States
- **Bounding Box (Pending):** `--signal-amber` border, 10% fill
- **Bounding Box (Approved):** `--signal-green` border, 8% fill, then REMOVED from set
- **Bounding Box (Rejected):** `--signal-red` border, 8% fill, triggers correction loop
- **Buttons:** Subtle glow on hover, 200ms transition, no harsh shadows

## Approval Flow
1. User views page with bounding boxes overlaying extracted data
2. Each match item in the sidebar shows extracted text + field
3. User clicks **APPROVE** - item is removed from the pending set, counters update
4. User clicks **REJECT** - notes field required, correction prompt generated, item stays flagged
5. Counters: `REMAINING: X | APPROVED: Y` update in real-time
6. Once REMAINING reaches 0 for a page, auto-advance to next page
