---
name: solidifai-bug-report
description: Help the user file a solidifai bug report on GitHub with one click. Use when repeated attempts at the same operation point to a genuine product defect (an engine crash, a tool error that is not the user's or your own mistake, geometry that stays wrong after real fixes), or when the user says "report a bug", "file an issue", or "this is broken". Gathers safe context and hands the user a prefilled, public issue link.
license: MIT
---

# solidifai bug report

> Invoke the `using-solidifai` skill first if you have not already this session; it orients you to this workspace and the `solidifai-cad` engine every skill here drives.

This skill turns a real defect into a well-formed GitHub issue the user can submit in one
click. It does not fix anything and it never files on its own. **solidifai-debugging** owns
getting a build working; come here only once debugging shows the problem is a genuine
product defect, or when the user asks to report one.

## When to use

- You have tried real fixes (see solidifai-debugging) and the same operation keeps failing
  again in a way that looks like a **product defect**, not a user mistake or your own
  modeling error: an engine crash or traceback that repeats, a tool that errors on valid
  input, geometry that stays wrong after genuine attempts.
- The user says "report a bug", "file an issue", "this is broken", or asks you to tell the
  maintainers.
- **Skip when:** the build just needs another debugging pass, the failure is a user typo or
  a missing `show(...)`, or you have not actually tried to fix it yet. Offer once per
  distinct failure; do not nag.

## The procedure

1. **Offer, do not assume.** Say plainly that this looks like a solidifai bug and ask if
   they want you to prepare a report. If they decline, drop it.
2. **Gather only safe context.** Collect what helps triage and is safe to share publicly:
   the operation you attempted, the exact error string or traceback, the engine status, and
   what you expected versus what happened.
3. **Never include sensitive information.** No file contents, no absolute paths, no secrets
   or tokens, and no proprietary design details, dimensions, or part names unless the user
   explicitly says it is fine to share them. Paraphrase logs rather than pasting raw dumps.
   The tool redacts home paths and secrets as a backstop, but you are the first line: keep
   it clean.
4. **Build the report with `report_issue`.** Call the `report_issue` tool with `title`,
   `what_happened`, and optional `steps` and `context`. It fills in the app version, OS, and
   a safe diagnostics block for you. **Never hand-assemble the GitHub URL yourself**;
   `report_issue` is the only correct way to build it, and it enforces the redaction and
   length limits.
5. **Show the preview and let the user decide.** Print the `preview` the tool returns so the
   user sees exactly what will be shared, and tell them this content is public. Give them
   the `url` to click. They can still edit everything on GitHub before submitting.
   Submitting is their choice; the click is the consent. You never submit anything.

## What the report carries

`report_issue` targets the repo's bug form, so a good report has a short `title`, a clear
`what_happened` (what you did, what you expected, what happened instead), optional `steps`
to reproduce, and a `context` field for the curated error text. The app version, operating
system, and a safe build fingerprint are added automatically. Keep every field readable and
free of anything the user would not want on a public issue.

## Cross-references

- **solidifai-debugging** - real fix attempts come first; this skill only opens once that
  points to a genuine product defect.
