---
name: mistakemate-control
description: Control MistakeMate daily review: inspect due questions, record correct or incorrect results, and prepare a verified printing link.
version: 0.1.0
metadata:
  hermes:
    tags: [education, mistakes, review, printing]
    requires_tools: [list_today_tasks, get_question, mark_attempt, prepare_print]
---

# MistakeMate Control

Use this skill for a user's own MistakeMate account when they ask to review a wrong question, report a result, or prepare a question for printing.

## Rules

- Read the current task list before choosing a question by order, subject, or priority.
- Before recording a result, identify the question in the reply and use only `correct` or `incorrect`.
- Do not reveal stored answers unless the user explicitly asks to check an answer.
- `prepare_print` only prepares an authenticated print-workspace link. State that no paper has been printed yet.
- Only proceed from a prepared link to an actual browser print action after the user explicitly confirms the selected question, copies, paper size, and template.
- Never use this integration to delete questions, edit account data, or access another user's records.

## First-time setup

If the MCP tools are unavailable, ask the user for permission to install the MistakeMate integration. Ask for the MistakeMate address and a newly created Hermes token, then run the repository's `integrations/hermes-mcp/install.py` with `--url` and `--token`. Do not paste the token into chat logs or source files. If an existing `mistakemate` MCP entry is found, explain that replacing it requires explicit user approval and the `--replace` option.

## Common workflows

### Today's review

1. Call `list_today_tasks`.
2. Summarize pending count, already completed count, and highest-priority reason.
3. Call `get_question` only for the question the user wants to work on.

### Record a result

1. Confirm which question the result belongs to.
2. Call `mark_attempt`.
3. Explain that an incorrect result will be prioritized in later review, while a correct result enters the spaced-review schedule.

### Prepare printing

1. Confirm the exact question(s) and intended template or paper size.
2. Call `prepare_print` for each question.
3. Give the returned link and say it opens a preselected MistakeMate print workspace.
4. Do not say “printed” until a browser print action has succeeded after explicit confirmation.
