# Magic Learning Bundle (.mlb) — Format Specification

Version: **1.0**
Extension: `.mlb`

---

## Purpose

An `.mlb` file packs all four lesson assets — the JSON data file and the three
MP3 audio files — into a single binary container.  The content is lightly
obfuscated with a rolling XOR cipher so that the raw files cannot be extracted
or played without knowledge of the secret key that is embedded in the app.

This is **not full encryption**.  A determined reverse-engineer who obtains the
compiled app binary can extract the key.  The goal is to prevent casual
downloading and direct playback of lesson audio, not to provide cryptographic
security.

---

## File Layout

The file is divided into two logical areas: a fixed **header** and a variable
**body** (manifest + data sections).

```
Offset    Length         Field
──────────────────────────────────────────────────────────────
0         4 bytes        Magic signature  (NOT obfuscated)
4         1 byte         Format version   (NOT obfuscated)
5         4 bytes        Manifest size    (NOT obfuscated)
9         manifest_size  Manifest JSON    (XOR obfuscated)
9+M       varies         JSON data section   (XOR obfuscated)
varies    varies         Story MP3 section   (XOR obfuscated)
varies    varies         Lexical MP3 section (XOR obfuscated)
varies    varies         Drills MP3 section  (XOR obfuscated)
```

`M` = manifest_size (read from bytes 5–8).

---

## Field Descriptions

### Magic signature — bytes 0–3  (4 bytes, plain)

Always the four ASCII bytes `M L R N` (hex `4D 4C 52 4E`).

A reader must reject any file whose first four bytes are not exactly `4D 4C 52 4E`.

### Format version — byte 4  (1 byte, plain)

Currently `0x01`.  Future breaking format changes will increment this value.
A reader should reject files with a version it does not recognise.

### Manifest size — bytes 5–8  (4 bytes, plain, big-endian uint32)

The number of bytes occupied by the obfuscated manifest, starting at byte 9.
This value is unobfuscated so the reader can allocate a buffer before decoding.

### Manifest — bytes 9 to (9 + manifest_size − 1)  (XOR obfuscated)

Once decoded the manifest is a compact UTF-8 JSON object:

```json
{
  "v": 1,
  "slug": "das-licht-des-leuchtturms-a2",
  "sections": {
    "json":    { "offset": 9482,     "size": 55786   },
    "story":   { "offset": 65268,    "size": 656396  },
    "lexical": { "offset": 721664,   "size": 9409004 },
    "drills":  { "offset": 10130668, "size": 8011916 }
  }
}
```

| Key                         | Type   | Meaning                                              |
|-----------------------------|--------|------------------------------------------------------|
| `v`                         | int    | Format version (must equal the header version byte)  |
| `slug`                      | string | Lesson slug (e.g. `das-licht-des-leuchtturms-a2`)   |
| `sections.<name>.offset`    | int    | **Absolute** byte offset of this section in the file |
| `sections.<name>.size`      | int    | Byte length of the (obfuscated) section              |

Section names are always `"json"`, `"story"`, `"lexical"`, and `"drills"`.

### Data sections  (XOR obfuscated, independently)

The four data sections follow the manifest in this canonical order:

1. `json`    — the raw UTF-8 lesson JSON (original `<slug>.json`)
2. `story`   — the raw story MP3 bytes   (original `<slug>-story.mp3`)
3. `lexical` — the raw lexical MP3 bytes (original `<slug>-lexical.mp3`)
4. `drills`  — the raw drills MP3 bytes  (original `<slug>-drills.mp3`)

Sections are contiguous with no padding between them.  The first section
begins immediately after the last manifest byte.

---

## XOR Obfuscation

### Key derivation

The 32-byte XOR key is derived from a passphrase string using SHA-256:

```
key_bytes = SHA-256( passphrase.encode('utf-8') )   // 32 bytes
```

The passphrase is **never stored** in the bundle.  It must be compiled into the
app as a constant.  The same passphrase always produces the same key.

### Encoding rule

For a single logical region (the manifest, or one data section), byte at
position `i` within that region is encoded as:

```
encoded[i] = plain[i]  XOR  key_bytes[i mod 32]
```

The key index **resets to zero at the start of every region**.  The manifest
and each of the four data sections are each independently encoded starting
from key index 0.  Key phase does **not** carry over between regions.

### Decoding rule

The operation is self-inverse — decoding is identical to encoding:

```
plain[i] = encoded[i]  XOR  key_bytes[i mod 32]
```

Apply to the manifest bytes (starting at key index 0) to recover the manifest
JSON.  Apply to each data section's bytes (starting at key index 0) to recover
the original file content.

---

## Reading Algorithm (pseudocode)

```
function open_mlb(file_path, passphrase):
    key = sha256(passphrase)

    f = open(file_path, 'rb')

    # 1. Verify magic
    magic = f.read(4)
    assert magic == b'MLRN'

    # 2. Check version
    version = f.read(1)[0]
    assert version == 1

    # 3. Read manifest size
    manifest_size = big_endian_uint32( f.read(4) )

    # 4. Decode manifest
    manifest_encoded = f.read(manifest_size)
    manifest_json    = xor(manifest_encoded, key)   // key index resets to 0
    manifest         = parse_json(manifest_json)

    return manifest, f, key


function read_section(manifest, f, key, section_name):
    info   = manifest['sections'][section_name]
    offset = info['offset']
    size   = info['size']

    f.seek(offset)
    encoded = f.read(size)
    return xor(encoded, key)                        // key index resets to 0
```

---

## Verification Checks

A conforming reader must reject a file if any of the following are true:

| Check                              | Error                                    |
|------------------------------------|------------------------------------------|
| Bytes 0–3 ≠ `MLRN`                | Not an MLB file                          |
| Byte 4 is an unknown version       | Unsupported format version               |
| File is shorter than `9 + M` bytes | Truncated or corrupt file                |
| Manifest JSON fails to parse       | Wrong passphrase or corrupt manifest     |
| Any section `offset + size` > file size | Truncated file                      |
| Manifest `v` ≠ header version byte | Version field mismatch                   |

---

## File Size Formula

```
total_file_size
  = 9                                      // fixed header
  + manifest_size                          // obfuscated manifest
  + sections.json.size
  + sections.story.size
  + sections.lexical.size
  + sections.drills.size
```

The obfuscated section sizes equal the original file sizes because XOR is a
byte-for-byte transform.

---

## Example: Byte Map for a Real Lesson

Using `das-licht-des-leuchtturms-a2` with source sizes:

| File                | Original size |
|---------------------|---------------|
| `.json`             | 55,786 bytes  |
| `-story.mp3`        | 656,396 bytes |
| `-lexical.mp3`      | 9,409,004 bytes |
| `-drills.mp3`       | 8,011,916 bytes |

Approximate (.mlb with ~473-byte manifest):

```
[0]        4 bytes   MLRN
[4]        1 byte    0x01
[5]        4 bytes   manifest_size ≈ 473
[9]        473 bytes obfuscated manifest JSON
[482]      55,786    obfuscated JSON section
[56,268]   656,396   obfuscated story MP3
[712,664]  9,409,004 obfuscated lexical MP3
[10,121,668] 8,011,916 obfuscated drills MP3
───────────────────────
Total ≈ 18,133,584 bytes  (18.1 MB)
```

*(Exact offsets are in the `sections` object inside the bundle itself.)*

---

## Design Decisions and Trade-offs

| Decision | Rationale |
|---|---|
| XOR, not AES | Zero library dependencies, negligible CPU overhead, suitable for the threat model (casual scraping, not nation-state attacks) |
| Independent key index per section | Allows random-access reads: seek to any section and decode without reading earlier sections first |
| Offsets are absolute | The reader just `seek(offset)` and reads – no bookkeeping |
| Header fields are unobfuscated | Magic + version can be validated before deriving the key |
| SHA-256 key derivation | Deterministic, no salt needed (the passphrase is already high-entropy), standard library in both Python and Dart |
| Manifest is also obfuscated | Prevents trivial inspection of the section map |

---

## Tooling

| Tool | Location | Purpose |
|---|---|---|
| `bundle_lesson.py` | `tools/bundle_lesson.py` | Create `.mlb` from a lesson folder |
| `bundle_lesson.py verify` | same file, `verify` subcommand | Validate an existing `.mlb` |

See `FLUTTER_INTEGRATION_GUIDE.md` for the Dart-side reader implementation.
