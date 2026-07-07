"""Tests for the updater-manifest notes cleaner (release-build.yml uses it)."""

from build_updater_notes import clean_release_notes

# A realistic release-please GitHub release body: no `## [version]` header (that's
# the release title), grouped sections, bold scopes, and trailing commit links.
RELEASE_BODY = """### Features

* **updater:** context-aware update UX ([abc1234](https://github.com/o/r/commit/abc1234))
* **settings:** split app vs workspace ([def5678](https://github.com/o/r/commit/def5678))

### Bug Fixes

* **ui:** windows-aware path display ([9012abc](https://github.com/o/r/commit/9012abc))
"""


def test_keeps_grouped_notes_verbatim_when_there_is_no_title():
    out = clean_release_notes(RELEASE_BODY)
    assert out.startswith("### Features")
    assert "### Bug Fixes" in out
    assert "context-aware update UX" in out
    # commit links + bold survive; the app renders them as markdown
    assert "](https://github.com/o/r/commit/abc1234)" in out


def test_strips_a_leading_version_header_so_the_app_title_is_not_doubled():
    body = "## [1.4.0](https://x/compare) (2026-07-07)\n\n### Features\n\n* a thing\n"
    out = clean_release_notes(body)
    assert out.startswith("### Features")  # the `## [1.4.0]` title line is gone
    assert "1.4.0" not in out


def test_strips_leading_h1_title_and_blank_lines():
    out = clean_release_notes("\n\n# solidifai 1.4.0\n\n### Features\n\n* a thing\n")
    assert out.startswith("### Features")


def test_drops_the_appended_download_guide():
    body = "### Features\n\n* a thing\n\n<!-- download-guide -->\n## Download\n\ninstaller...\n"
    out = clean_release_notes(body)
    assert "Download" not in out
    assert "installer" not in out
    assert out.strip().endswith("* a thing")


def test_empty_body_is_empty_notes():
    assert clean_release_notes("") == ""
    assert clean_release_notes("\n\n") == ""


def test_keeps_group_subheaders_h3():
    # `###` group headers must not be mistaken for the version title and stripped.
    out = clean_release_notes("### Features\n\n* only group\n")
    assert out.startswith("### Features")
