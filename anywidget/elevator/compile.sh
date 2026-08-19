#!/usr/bin/env bash
# Build report.ipynb into an ACM-style (acmart, manuscript format) PDF.
#
# Pipeline:
#   1. prepare_acm_notebook.py strips the title/author markdown cells into
#      notebook metadata and writes build/report_acm.ipynb.
#   2. jupyter nbconvert --to latex, using the latex_templates/acm template
#      (acmart docclass + per-author \affiliation blocks), extracting any
#      cell-output images into build/.
#   3. xelatex (twice, for cross references) against acmart.cls, unzipped
#      from acmart-primary.zip into acmart-primary/.
#
# Output: report-acm.pdf in this directory.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
REPORT_DIR="$(cd ../../report && pwd)"
ROOT_DIR="$(cd ../.. && pwd)"

PY="$ROOT_DIR/.venv/bin/python"
JUPYTER="$ROOT_DIR/.venv/bin/jupyter"
ACMART_SRC="$REPORT_DIR/acmart-primary/acmart-primary"
BUILD_DIR="$REPORT_DIR/build"
TEMPLATE_DIR="$REPORT_DIR/latex_templates"
NOTEBOOK="Elevator.ipynb"

if [ ! -x "$PY" ]; then
  echo "error: $PY not found -- run 'uv sync' at the repo root first." >&2
  exit 1
fi

if [ ! -f "$ACMART_SRC/acmart.cls" ]; then
  echo "error: acmart.cls not found under $ACMART_SRC" >&2
  echo "       unzip acmart-primary.zip in $REPORT_DIR first:" >&2
  echo "       unzip acmart-primary.zip -d acmart-primary" >&2
  exit 1
fi

if ! command -v xelatex >/dev/null 2>&1; then
  echo "error: xelatex not found on PATH (need a TeX Live install with acmart's deps)." >&2
  exit 1
fi

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

echo "==> Extracting title/author metadata"
"$PY" "$REPORT_DIR/prepare_acm_notebook.py" "$NOTEBOOK" "$BUILD_DIR/Elevator.ipynb"

echo "==> Copying acmart class files"
cp "$ACMART_SRC/acmart.cls" "$BUILD_DIR/"
cp "$ACMART_SRC/ACM-Reference-Format.bst" "$BUILD_DIR/"

echo "==> Copying externally-referenced image assets"
# Markdown cells reference these by relative path (not as notebook
# attachments/cell outputs), so nbconvert never copies them into the
# output dir on its own.
[ -f "$REPORT_DIR/image18.png" ] && cp "$REPORT_DIR/image18.png" "$BUILD_DIR/"
[ -d "$REPORT_DIR/assets" ] && cp -r "$REPORT_DIR/assets" "$BUILD_DIR/"

cd "$ROOT_DIR/anywidget/elevator/"
echo "==> Converting notebook to LaTeX (nbconvert, acmart template)"
"$JUPYTER" nbconvert --to latex \
  --execute \
  --ExecutePreprocessor.store_widget_state=True \
  --template acm \
  --TemplateExporter.extra_template_basedirs="$TEMPLATE_DIR" \
  --output report \
  --output-dir "$BUILD_DIR" \
  "$BUILD_DIR/Elevator.ipynb"

echo "==> Normalizing image files for xelatex (webp -> png, fixing mislabeled extensions)"
"$PY" - "$BUILD_DIR" <<'PYEOF'
import pathlib
import sys

from PIL import Image

build_dir = pathlib.Path(sys.argv[1])
tex_file = build_dir / "report.tex"
text = tex_file.read_text()

# xelatex/pdftex.def only understands PNG, JPEG and PDF raster data --
# convert anything else (webp, etc.) to PNG and rewrite the .tex reference.
for webp_path in build_dir.rglob("*.webp"):
    png_path = webp_path.with_suffix(".png")
    Image.open(webp_path).convert("RGBA").save(png_path)
    rel_webp = webp_path.relative_to(build_dir).as_posix()
    rel_png = png_path.relative_to(build_dir).as_posix()
    text = text.replace(rel_webp, rel_png)

tex_file.write_text(text)

# Some assets are mislabeled (e.g. an animated capture saved as *.png that
# is actually GIF-encoded) -- pdftex's libpng chokes on those even though
# the extension looks fine. Detect a format/extension mismatch and
# re-encode in place so the filename (and .tex reference) stay the same.
ext_format = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG"}
for path in build_dir.rglob("*"):
    expected = ext_format.get(path.suffix.lower())
    if expected is None or not path.is_file():
        continue
    with Image.open(path) as im:
        im.load()
        if im.format == expected:
            continue
        print(f"    fixing mislabeled image: {path.relative_to(build_dir)} "
              f"(was {im.format}, named as {expected})")
        if expected == "JPEG":
            im.convert("RGB").save(path, format=expected)
        else:
            im.convert("RGBA").save(path, format=expected)
PYEOF

echo "==> Running xelatex"
cd "$BUILD_DIR"
for pass in 1 2; do
  xelatex -interaction=nonstopmode -halt-on-error report.tex >xelatex.log \
    || { tail -n 60 xelatex.log; exit 1; }
done

cp report.pdf "$REPORT_DIR/report-acm.pdf"
echo "==> Wrote $REPORT_DIR/report-acm.pdf"
