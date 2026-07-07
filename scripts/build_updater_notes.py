"""Clean release notes for the updater manifest (latest.json `notes`).

The GitHub release body (release-please generated) is reused as the in-app
"What's new" text. Before it goes into the manifest we drop:
  * the appended download guide (present when a release job is re-run), and
  * a leading version/title header (`#` or `##`) plus any blank lines before it,
    since the app prints its own "What's new in vX" and a header here would
    double it.
Group subheaders (`###`) and everything else are kept; the app renders the rest
as markdown. Imported by the "Build updater manifest" step in release-build.yml.
"""

from __future__ import annotations

import pathlib
import re
import sys

GUIDE_MARKER = "<!-- download-guide -->"


def clean_release_notes(body: str) -> str:
    """Return the release body trimmed for use as manifest notes (see module doc)."""
    body = body.split(GUIDE_MARKER)[0]
    lines = body.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and re.match(r"^#{1,2}\s", lines[0]):
        lines.pop(0)
    return "\n".join(lines).strip()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    sys.stdout.write(clean_release_notes(text))
