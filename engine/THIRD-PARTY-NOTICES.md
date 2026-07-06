# Third-party notices (engine)

The engine bundle ships a standalone Python interpreter plus the engine's
locked dependency closure. Every bundled package keeps its own license text
in its `*.dist-info/licenses/` (or `*.dist-info/`) directory inside the
bundle's `site-packages` tree.

## fpdf2 (LGPL-3.0-only)

This product uses the fpdf2 library (https://github.com/py-pdf/fpdf2) for
PDF technical-drawing export (`solidifai_engine/drawing/backends.py`).
fpdf2 is licensed under the GNU Lesser General Public License v3.0
(LGPL-3.0-only), not under this project's Apache-2.0 license.

fpdf2 ships unmodified, as pure-Python source, in the bundle's
user-replaceable `site-packages` tree, so it can be inspected, modified,
and replaced with a compatible version as the LGPL requires.

License texts:

- GNU LGPL v3.0: [licenses/LGPL-3.0-only.txt](licenses/LGPL-3.0-only.txt)
  (also shipped in the bundle at
  `site-packages/fpdf2-*.dist-info/licenses/LICENSE`)
- GNU GPL v3.0, which the LGPL v3.0 incorporates by reference:
  [licenses/GPL-3.0-only.txt](licenses/GPL-3.0-only.txt)

These license texts apply to fpdf2 only. solidifai itself is licensed under
the Apache License 2.0; see `LICENSE` at the repository root.
