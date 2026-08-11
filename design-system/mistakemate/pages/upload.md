# Upload Page Overrides

> **PROJECT:** MistakeMate
> **Generated:** 2026-08-11 13:16:42
> **Page Type:** General

> ⚠️ **IMPORTANT:** Rules in this file **override** the Master file (`design-system/MASTER.md`).
> Only deviations from the Master are documented here. For all other rules, refer to the Master.

---

## Page-Specific Rules

### Layout Overrides

- **Max Width:** 1200px
- **Layout:** Responsive grid

### Spacing Overrides

- No overrides — use Master spacing

### Typography Overrides

- No overrides — use Master typography

### Color Overrides

- No overrides — use Master colors

### Component Overrides

- No overrides — use Master component specs

---

## Page-Specific Components

### OCR Crop Dialog

- Desktop uses a centered modal up to 960px; phone uses a bottom-aligned full-width sheet without horizontal scrolling.
- Keep the image on a dark neutral canvas and use the existing orange accent only for the crop boundary and confirmation action.
- Provide eight visible resize handles, drag-to-move, drag-outside-to-redraw, arrow-key movement, and `Shift + Arrow` resizing.
- Close, cancel, whole-image, and confirm controls must remain at least 44px high with visible keyboard focus.
- Lock background scrolling and keep keyboard focus inside the dialog until it is closed.
- Cropping changes only the OCR input region; the stored original image remains untouched.

---

## Recommendations

- Refer to MASTER.md for all design rules
- Add specific overrides as needed for this page
