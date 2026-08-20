# TiLiA Icons

## Toolbar icons
- Duplicated into the folders:
    - `tiliaDark/actions/256`   (with a primary color of `#fff`), and
    - `tiliaLight/actions/256`  (with a primary color of `#000`)

    (Duplicated so that the icons remain visible when the display switches between dark and light mode.)

### Dimensions and stroke conventions
- `viewBox="0 0 256 256"`, no explicit `width`/`height` attribute.
- Solid strokes (outlines, arrows/chevrons): `stroke-width:16`, `stroke-linecap:round`, `stroke-linejoin:round`, `fill:none`.
- Dashed strokes (e.g. an insertion point or a boundary being added): same `stroke-width:16`, plus `stroke-dasharray:16,32` — dash length equals the stroke width, gap is double the stroke width.
- Solid filled shapes with no outline (e.g. background reference blocks): `fill:<color>`, `stroke-width:0`.
- Don't add a `px` unit suffix to `stroke-width`/`stroke-dashoffset` values — plain numbers, matching the rest of the set.

## Other icons (displayed in view, etc.)
- Only one copy needed in `hicolor/actions/256`
