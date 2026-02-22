# CLAUDE.md — Shift Manager

This file provides guidance for AI assistants working on this codebase.

## Project Overview

Shift Manager is a Japanese shift-scheduling PWA (Progressive Web App) for tracking work schedules across multiple team members. It is a **single-file, zero-build application** — the entire codebase lives in `index.html`.

- **Language**: JavaScript (JSX transpiled in-browser via Babel Standalone)
- **Framework**: React 18 (loaded from CDN)
- **Persistence**: Browser `localStorage` only — no backend, no database
- **Target audience**: Japanese shift workers; all UI text is in Japanese

---

## Repository Structure

```
shift-manager/
└── index.html   ← entire application (873 lines)
```

There are no other source files, no build tools, no `package.json`, and no test suite. Everything is inline in `index.html`.

---

## Architecture

### Single-file layout (`index.html`)

| Section | Lines | Description |
|---|---|---|
| HTML head / meta | 1–36 | PWA meta tags, viewport, theme color |
| Global CSS | 12–32 | Reset, animations, hover states, safe-area insets |
| CDN scripts | 37–41 | React 18, ReactDOM 18, Babel Standalone 7 |
| Initial data | 46–79 | Hardcoded March 2026 schedule for 成田 |
| Helpers | 83–110 | `dateKey`, `calcHours`, `defaultEndTime`, `formatHours`, `storage` |
| SVG icons | 112–119 | Inline icon components |
| `MEMBERS` constant | 121 | `["成田", "正田", "尾谷", "淵原"]` |
| `ShiftManager` | 124–539 | Root component — all state lives here |
| `ImportModal` | 542–730 | Import dialog (Claude AI / JSON tabs) |
| `CalendarView` | 732–800 | Calendar grid view |
| `ListView` | 803–866 | List view |
| React root render | 869–870 | `ReactDOM.createRoot(...).render(...)` |

### React components

**`ShiftManager`** (root)
- Owns all application state (current member, year/month, shifts, modal visibility, select mode)
- Handles month navigation with swipe gesture support
- Renders header, stats bar, view toggle, and delegates to `CalendarView` or `ListView`
- Contains inline edit modal and delete confirmation dialogs

**`CalendarView`**
- 7-column grid, color-coded shift dots (early/late shift detection based on start time)
- Shows coworkers on same day, today highlight, memo indicators

**`ListView`**
- Row-per-day list with hours calculation
- Multi-select mode for bulk deletion

**`ImportModal`**
- "Scan" tab: prompt text the user copies into a Claude AI chat session, then pastes the AI's JSON response back
- "JSON" tab: raw JSON paste-in
- Normalises unicode quotes/dashes before parsing

### Data model

Shifts are stored in `localStorage` with the key pattern:

```
shifts:{memberName}:{YYYY-MM}
```

Example key: `shifts:成田:2026-03`

Each value is a JSON string of an object keyed by ISO date strings:

```json
{
  "2026-03-04": {
    "status": "出勤",
    "startTime": "09:30",
    "endTime": "18:30",
    "breakTime": 60,
    "memo": ""
  }
}
```

**Field values:**
- `status`: `"出勤"` (working) | `"休日"` (day off)
- `startTime` / `endTime`: `"HH:MM"` 24-hour string, or `""` if unset
- `breakTime`: break duration in minutes (`0`, `30`, `60`, `90`); defaults to `60`
- `memo`: free-text string

**Legacy migration**: On load, if no member-specific key exists for 成田, the app checks the old `shifts:{YYYY-MM}` key and migrates it automatically.

**Seed data**: If no data exists at all for `成田 / 2026-03`, `MARCH_2026_DATA` is written to `localStorage` automatically.

---

## Key Conventions

### Japanese UI text
All user-visible strings are in Japanese. Do not introduce English strings into the UI. Core vocabulary:

| Japanese | Meaning |
|---|---|
| 出勤 | Working (shift status) |
| 休日 | Day off (shift status) |
| 開始 | Start time |
| 終了 | End time |
| 休憩 | Break |
| メモ | Memo/notes |
| 日 月 火 水 木 金 土 | Sun Mon Tue Wed Thu Fri Sat |

### Members (`MEMBERS` constant)
The four members are hardcoded: `["成田", "正田", "尾谷", "淵原"]`. Adding or renaming a member requires updating this array at line 121 and ensuring no member-specific logic elsewhere is broken.

### Storage key format
Always use the helper `dateKey(y, m, d)` to produce date strings. Never hand-build date keys. The storage key for a member's month data is:

```js
`shifts:${member}:${year}-${String(month).padStart(2,"0")}`
```

### Hours calculation
Use `calcHours(startTime, endTime, breakMin)`. It returns `null` if either time is missing. `breakMin` defaults to `60`. Result is a floating-point number of hours.

### No build step
There is no compilation, bundling, or build command. Open `index.html` in a browser to run the app. Changes take effect on page reload. JSX is transpiled at runtime by Babel Standalone.

### Inline styling
All styles are inline JavaScript objects passed to `style={}` props, or class names defined in the `<style>` block in the HTML head. There is no CSS module or external stylesheet. Keep new styles consistent with this pattern.

### Animations
Month transitions use CSS classes `slide-in-left` and `slide-in-right` (defined in the `<style>` block). The `slideDir` state in `ShiftManager` controls which class is applied.

---

## Development Workflow

### Running locally
```bash
# Any static file server works, e.g.:
python3 -m http.server 8080
# Then open http://localhost:8080
```
Or just open `index.html` directly in a browser (file:// protocol works for this app).

### Making changes
1. Edit `index.html` directly.
2. Reload the browser.
3. Use browser DevTools console to inspect `localStorage` state.

### Inspecting stored data
In the browser console:
```js
// View all shift keys
Object.keys(localStorage).filter(k => k.startsWith("shifts:"))

// View a specific month for 成田
JSON.parse(localStorage.getItem("shifts:成田:2026-03"))

// Clear all shift data
Object.keys(localStorage).filter(k => k.startsWith("shifts:")).forEach(k => localStorage.removeItem(k))
```

### No automated tests
There is no test framework. Testing is done manually in the browser. When making changes, verify:
- Calendar view renders correctly for the current month
- Navigating months forward/backward works (including year boundaries)
- Editing and saving a shift entry persists across page reload
- Switching members shows the correct data
- Import modal parses valid JSON correctly
- Stats (work days, off days, total hours) update after edits

---

## Common Patterns

### Adding a new shift field
1. Add the field to the `editData` state initialisation in `openEdit()` (line ~202).
2. Add the corresponding UI control inside the edit modal JSX in `ShiftManager`.
3. Ensure `saveEdit()` passes the field through via `{ ...editData }`.
4. Update `ImportModal`'s JSON parsing logic if the field should be importable.

### Adding a new member
1. Add the name to `MEMBERS` at line 121.
2. No other changes required — the member selector and storage are driven by `MEMBERS`.

### Changing the default break duration
The default is `60` minutes. This appears in `openEdit()` when creating a new entry and in `calcHours` call sites. Search for `breakTime: 60` and `breakMin = 60` to find all occurrences.

---

## Import via Claude AI

The ImportModal "Scan" tab provides a prompt that the user sends (with a screenshot of a shift schedule) to a Claude AI chat session. The expected JSON response format is:

```json
{
  "2026-04-01": { "status": "出勤", "startTime": "09:30", "endTime": "18:30", "memo": "" },
  "2026-04-02": { "status": "休日", "startTime": "", "endTime": "", "memo": "" }
}
```

The import normalises:
- Full-width colons `：` → `:`
- Smart/curly quotes → straight quotes
- Em-dashes and en-dashes → hyphens

---

## Git History Notes

Historical commits use the message `index.html を更新` (Japanese: "updated index.html"). New commits may use English or Japanese — either is acceptable. The working branch is `claude/add-claude-documentation-Mvfmx`.
