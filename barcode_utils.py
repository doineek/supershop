"""
barcode_utils.py
-----------------
Turns a product's SKU (or invoice number) into a real, scannable Code128
barcode image (as SVG).

IMPORTANT FIX
-------------
python-barcode's SVGWriter draws every bar using physical units, e.g.
`x="1.500mm" width="0.500mm"`. The previous version of this file only
stripped the "mm" suffix from the *root* <svg> width/height and added a
viewBox using the same numbers - but left "mm" on every internal <rect>.
Mixing a unitless viewBox with mm-suffixed child coordinates makes browsers
apply an extra physical-unit conversion (1mm = 96/25.4 px) on top of the
viewBox scaling, so the bars end up positioned far outside the visible
viewBox. The result is a barcode that looks squashed/cut-off on screen and
does not scan at all.

The fix: strip the "mm" suffix from every coordinate/dimension in the SVG
(not just the root tag), so the whole document lives in one consistent,
unitless coordinate space that exactly matches the viewBox. Width/height on
the root tag are then set to 100% so the barcode fills whatever box it is
placed in, scaling uniformly (bar-width ratios are preserved) and remaining
scannable at any size.
"""

import io
import re
import barcode
from barcode.writer import SVGWriter

# Matches any numeric attribute value written with an explicit "mm" suffix,
# e.g. x="1.500mm", width="0.500mm", y="1.000mm", height="14.000mm"
_MM_ATTR_RE = re.compile(r'="([\d.]+)mm"')


def generate_barcode_svg(data: str) -> str:
    """Return a scannable Code128 SVG barcode string for the given data
    (a SKU, invoice number, or any other short code)."""
    clean_data = str(data).strip()
    code = barcode.get("code128", clean_data, writer=SVGWriter())
    buffer = io.BytesIO()

    code.write(buffer, options={
        "write_text": False,
        "module_height": 14,
        "module_width": 0.25,
        "quiet_zone": 1.5,
    })

    svg = buffer.getvalue().decode("utf-8")

    # 1) Read the root <svg> width/height (in mm) so we can build a matching
    #    viewBox before we strip the units out.
    svg_tag_match = re.search(r'<svg[^>]+>', svg)
    if svg_tag_match:
        original_svg_tag = svg_tag_match.group(0)
        w_match = re.search(r'width="([\d.]+)mm"', original_svg_tag)
        h_match = re.search(r'height="([\d.]+)mm"', original_svg_tag)

        if w_match and h_match:
            w = float(w_match.group(1))
            h = float(h_match.group(1))

            new_svg_tag = original_svg_tag
            if "viewBox=" not in new_svg_tag:
                new_svg_tag = new_svg_tag.replace(
                    '<svg ',
                    f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
                )

            # Root element fills 100% of its container.
            new_svg_tag = re.sub(r'width="[\d.]+mm"', 'width="100%"', new_svg_tag, count=1)
            new_svg_tag = re.sub(r'height="[\d.]+mm"', 'height="100%"', new_svg_tag, count=1)

            svg = svg.replace(original_svg_tag, new_svg_tag, 1)

    # 2) Strip the "mm" suffix from every remaining coordinate/dimension
    #    (all the individual <rect> bars) so they live in the same unitless
    #    coordinate space as the viewBox above. This is the critical fix -
    #    without it the bars are mis-positioned and the barcode won't scan.
    svg = _MM_ATTR_RE.sub(lambda m: '="%s"' % m.group(1), svg)

    return svg
