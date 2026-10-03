# File formats (reverse engineered from TIM 3.5.0.22149)

Everything below was derived by inspection; `tools/rdb.py` round-trips real files
byte-for-byte, which is the strongest evidence that the layout is right.

## `.rdb` — resource container

TIM ships four of them:

```
Resource.3.5.0.22149\Res.rdb              ~6700 files, images/sounds/scripts
Resource.3.5.0.22149\Xtml.rdb             ~1550 files, one .gmd per UI page
Resource.3.5.0.22149\Themes\Default.rdb   ~2200 files, shared skins + theme.xml
Resource.3.5.0.22149\Data.rdb             avatars/faces only, no .gmd at all
```

Layout:

```
0x00  16 bytes   magic  53 1E 98 20 4F 85 42 F0
0x10  u32        item count
0x14  i64        header size  (always 36)
0x1C  i64        name blob size
0x24  ...        index entries:
                     UTF-16LE name, NUL terminated
                     i64 offset      relative to  (36 + name blob size)
                     i64 size
...              payload
```

Unpack: `python tools/rdb.py unpack FILE.rdb outdir`
Repack: `python tools/rdb.py pack outdir FILE.rdb --manifest ORIGINAL.rdb`

Repacking with the original as `--manifest` keeps the file order and names of items
that were not modified, so the round trip is byte-identical.

## `.gft` — a PNG in a wrapper

```
0x00  3 bytes   'TGF'
0x10  u32       offset of the PNG payload
0x1C  'NINE'    present only for nine-patch images; margins follow
...             standard PNG
```

Replacing the PNG payload (keeping the header) is enough to restyle a bitmap.
`skinpatch.py` does this; `load_png_bytes` here is tolerant about which of the two
offsets is authoritative.

## `.gmd` — a compiled skin

A `.gmd` is a serialised control tree with property records. Two encodings coexist:

* **TD records** — marker `TD 01 01`, a kind byte, `00`, a type code and a
  `u16` length; the payload is XORed with `0xFF ^ (length & 0xFF)`.
* **compact records** — a single tag byte, a `u16` length, then the payload.

Either way a property looks like:

```
<name bytes> <u16 length> <payload>
```

and a colour property is exactly 4 payload bytes. `gmdscan.py` finds them; because
both scanners can hit the same 4 bytes, results must be de-duplicated by the
**absolute offset of the value** before being rewritten.

## `theme.xml` — `Themes\Default.rdb\appframework\config\theme.xml`

276 named colours in `<TG name="...">` groups (`TextColor`, `TIMColor`, `Color`,
`Rich_TextColor`, `BorderColor`, `FCColor`, ...). It looks authoritative and it is
**not read at runtime** in 3.5 — see TRAPS.md, entry 4. It is still worth patching
because TIM caches it (entry 5) and some builds do consult the cache.

Also note `MaskColor = 0xFF00FF` is the transparency colour key and must never be
changed.

## Colours

TIM stores colours as **`0xAARRGGBB`**. Values read out of a `.gmd` with
`struct.unpack("<I")` follow that convention, so `0xFF1E1E1F` is `RGB(30,30,31)`.

## Text colour resolution (why resources are not enough)

```
                     ┌─────────────────────────────────────────┐
  AutoColor skins ──►│ GF::Util::Text::GetTextColor(level)     │──► white/black
  (bare `color` is   │  white level -> BLACK text              │
   the level input)  └─────────────────────────────────────────┘

                     ┌─────────────────────────────────────────┐
  chat body/list ───►│ arkGraphic!arkCanvasSetColor(canvas,    │──► literal 0xFF000000
                     │   0xFF000000)  -- hardcoded             │
                     └─────────────────────────────────────────┘

                     ┌─────────────────────────────────────────┐
  member list /  ───►│ gdi32!SetTextColor(dc, 0xFF000000)      │──► literal black
  group bulletin     │  called from GF.dll+0x13050             │
                     └─────────────────────────────────────────┘
```

Only the first row is reachable from a skin file, and even then the field to edit
is the *input level*, not the text colour.
