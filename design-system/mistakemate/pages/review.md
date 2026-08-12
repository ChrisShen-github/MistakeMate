# Review Page Overrides

> **PROJECT:** MistakeMate
> **Page Type:** OCR question confirmation

---

## Page-Specific Rules

### Layout Overrides

- Desktop keeps the editable question card and original image in one reading flow; phone collapses the form to a single column without horizontal scrolling.
- Keep OCR source text behind a native disclosure control so the editable question remains the primary task.

### Component Overrides

- Every input has a persistent visible label. Save actions provide an inline success or error message.
- Difficulty uses five labelled, keyboard-focusable star buttons; the selected value is not communicated by colour alone.
- Primary confirmation and secondary draft-save controls are at least 44px high and remain easy to reach on a phone.
- Preserve the original uploaded image as the source of truth and clearly tell the user to compare it before confirming.

### Multi-part Question Editor

- Keep the common stem once, then show root parts and indented child parts in reading order.
- Use progressive disclosure: final answers stay visible; scoring points, answer space, per-part difficulty, knowledge points, and error type live behind an expandable section.
- Answers are optional. Keep answer and solution inputs inside a clearly labelled disclosure, collapsed when empty, so question-only collection remains the primary path.
- When answers are provided, fill-in questions use one labelled input per blank; calculation and proof questions separate the final answer from the full solution.
- Automatic structure detection changes only the current draft until the user explicitly saves it.
- Preserve the simple single-answer form when no numbered parts are detected.
