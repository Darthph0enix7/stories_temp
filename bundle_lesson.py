#!/usr/bin/env python3
"""
bundle_lesson.py
----------------
Magic Learning Bundle (.mlb) creator.

Packs a lesson folder (1 JSON + 3 MP3 files) into a single binary .mlb file
with lightweight XOR obfuscation derived from a passphrase.

Usage
-----
  # Single lesson
  python bundle_lesson.py bundle --input <lesson_folder> [--output <output.mlb>] [--key <passphrase>]

  # Batch bundle all lessons in a directory
  python bundle_lesson.py batch-bundle --input <parent_folder> [--key <passphrase>] [--output-dir <dir>]

Examples
--------
  # Bundle a single lesson (with explicit key)
  python bundle_lesson.py bundle \
    --input sample_stories/das-licht-des-leuchtturms-a2 \
    --key MySecretAppKey

  # Bundle a single lesson (using bundle_password env var)
  python bundle_lesson.py bundle \
    --input sample_stories/das-licht-des-leuchtturms-a2

  # Batch bundle all lessons in current directory (uses bundle_password env var)
  python bundle_lesson.py batch-bundle --input .

  # Batch bundle with explicit output directory
  python bundle_lesson.py batch-bundle --input . --output-dir ./bundles

See MLB_FORMAT_SPEC.md for the full binary format documentation.
"""

import argparse
import hashlib
import itertools
import json
import os
import struct
import sys

# ── Constants ────────────────────────────────────────────────────────────────

MAGIC: bytes = b'MLRN'          # 4-byte file signature
FORMAT_VERSION: int = 1          # current format version byte
HEADER_SIZE: int = 9             # magic(4) + version(1) + manifest_size(4)
SECTION_ORDER: list[str] = ['json', 'story', 'lexical', 'drills']


# ── Key derivation ────────────────────────────────────────────────────────────

def derive_key(passphrase: str) -> bytes:
    """Derive a 32-byte XOR key from an arbitrary passphrase via SHA-256.

    The same passphrase always produces the same key.  The key is never stored
    in the bundle or transmitted anywhere – it must be hardcoded in the app.
    """
    return hashlib.sha256(passphrase.encode('utf-8')).digest()


# ── XOR obfuscation ───────────────────────────────────────────────────────────

def xor_bytes(data: bytes, key: bytes) -> bytes:
    """XOR every byte of *data* with the cycling *key*.

    The key index resets to 0 at the start of every call, so each logical
    region (manifest, json section, story section, …) is independently
    obfuscated.  Calling xor_bytes twice with the same key is self-inverse –
    i.e. xor_bytes(xor_bytes(data, key), key) == data.
    """
    return bytes(b ^ k for b, k in zip(data, itertools.cycle(key)))


# ── File discovery ────────────────────────────────────────────────────────────

def find_lesson_files(
    folder: str,
) -> tuple[str, str, str, str, str]:
    """Locate the 4 required lesson files inside *folder*.

    Returns (slug, json_filename, story_filename, lexical_filename, drills_filename).

    Resolution order:
    1. Slug derived from the folder name  →  <slug>.json / <slug>-story.mp3 / …
    2. Fuzzy fallback: any .json file + any MP3 containing 'story'/'lexical'/'drill'
    """
    folder = os.path.normpath(folder)
    all_files = os.listdir(folder)
    slug = os.path.basename(folder)

    json_file: str | None = None
    mp3_story: str | None = None
    mp3_lexical: str | None = None
    mp3_drills: str | None = None

    # Pass 1 – exact slug-based names
    for f in all_files:
        if f == f'{slug}.json':
            json_file = f
        elif f == f'{slug}-story.mp3':
            mp3_story = f
        elif f == f'{slug}-lexical.mp3':
            mp3_lexical = f
        elif f == f'{slug}-drills.mp3':
            mp3_drills = f

    # Pass 2 – fuzzy fallback if any are still missing
    if json_file is None:
        candidates = [f for f in all_files if f.endswith('.json') and not f.startswith('.')]
        if candidates:
            json_file = candidates[0]
            slug = json_file.removesuffix('.json')

    if mp3_story is None:
        candidates = [f for f in all_files if 'story' in f.lower() and f.endswith('.mp3')]
        mp3_story = candidates[0] if candidates else None

    if mp3_lexical is None:
        candidates = [f for f in all_files if 'lexical' in f.lower() and f.endswith('.mp3')]
        mp3_lexical = candidates[0] if candidates else None

    if mp3_drills is None:
        candidates = [f for f in all_files if 'drill' in f.lower() and f.endswith('.mp3')]
        mp3_drills = candidates[0] if candidates else None

    # Collect any missing entries for a clear error message
    missing: list[str] = []
    if json_file is None:
        missing.append('JSON data file (<slug>.json)')
    if mp3_story is None:
        missing.append('story MP3 (<slug>-story.mp3)')
    if mp3_lexical is None:
        missing.append('lexical MP3 (<slug>-lexical.mp3)')
    if mp3_drills is None:
        missing.append('drills MP3 (<slug>-drills.mp3)')

    if missing:
        raise FileNotFoundError(
            f'Missing required files in {folder}:\n  ' + '\n  '.join(missing)
        )

    return slug, json_file, mp3_story, mp3_lexical, mp3_drills  # type: ignore[return-value]


# ── Manifest builder ──────────────────────────────────────────────────────────

def _build_manifest_bytes(
    slug: str,
    section_sizes: dict[str, int],
    data_region_start: int,
) -> bytes:
    """Return the raw (unobfuscated) UTF-8 manifest JSON for the given sizes.

    *data_region_start* is the absolute file offset where the first data
    section begins (i.e. HEADER_SIZE + manifest_size).
    """
    sections: dict[str, dict[str, int]] = {}
    cursor = data_region_start
    for label in SECTION_ORDER:
        size = section_sizes[label]
        sections[label] = {'offset': cursor, 'size': size}
        cursor += size

    manifest_obj = {
        'v': FORMAT_VERSION,
        'slug': slug,
        'sections': sections,
    }
    return json.dumps(manifest_obj, separators=(',', ':')).encode('utf-8')


def _resolve_manifest(
    slug: str,
    section_sizes: dict[str, int],
) -> bytes:
    """Two-pass manifest construction that handles offset digit-boundary shifts.

    Building the manifest requires knowing its own size (to compute section
    offsets), but its size depends on the digit count of those offsets.
    Two iterations are always sufficient because a second shift cannot occur
    once the first pass has already shifted digit boundaries.
    """
    # Pass 1 – estimate with a placeholder to measure manifest byte length
    dummy = _build_manifest_bytes(slug, section_sizes, data_region_start=HEADER_SIZE + 99999)
    estimated_size = len(dummy)

    # Pass 2 – build with real start offset
    real_start = HEADER_SIZE + estimated_size
    real_manifest = _build_manifest_bytes(slug, section_sizes, data_region_start=real_start)

    # Guard against the edge case where a digit boundary shifted the size
    if len(real_manifest) != estimated_size:
        real_start = HEADER_SIZE + len(real_manifest)
        real_manifest = _build_manifest_bytes(slug, section_sizes, data_region_start=real_start)

    return real_manifest


# ── Core bundler ──────────────────────────────────────────────────────────────

def bundle(
    folder: str,
    output_path: str,
    passphrase: str,
    verbose: bool = True,
) -> str:
    """Create an .mlb bundle from *folder* and write it to *output_path*.

    Returns the absolute path of the written file.
    """
    key = derive_key(passphrase)

    slug, json_name, story_name, lexical_name, drills_name = find_lesson_files(folder)

    # Map section labels to source file names
    source_names = {
        'json': json_name,
        'story': story_name,
        'lexical': lexical_name,
        'drills': drills_name,
    }

    # ── Read source files ────────────────────────────────────────────────────
    raw_sections: dict[str, bytes] = {}
    for label in SECTION_ORDER:
        path = os.path.join(folder, source_names[label])
        with open(path, 'rb') as f:
            raw_sections[label] = f.read()
        if verbose:
            print(f'  read {label:8s}  {len(raw_sections[label]):>10,} bytes  ({source_names[label]})')

    section_sizes = {label: len(raw_sections[label]) for label in SECTION_ORDER}

    # ── Build manifest ───────────────────────────────────────────────────────
    manifest_raw = _resolve_manifest(slug, section_sizes)
    manifest_obfuscated = xor_bytes(manifest_raw, key)
    manifest_size = len(manifest_obfuscated)

    # ── Obfuscate data sections independently ────────────────────────────────
    obfuscated_sections: dict[str, bytes] = {
        label: xor_bytes(raw_sections[label], key) for label in SECTION_ORDER
    }

    # ── Write output file ────────────────────────────────────────────────────
    output_path = os.path.abspath(output_path)
    with open(output_path, 'wb') as out:
        # Fixed header (unobfuscated)
        out.write(MAGIC)                             # bytes 0–3
        out.write(bytes([FORMAT_VERSION]))           # byte  4
        out.write(struct.pack('>I', manifest_size))  # bytes 5–8

        # Obfuscated manifest
        out.write(manifest_obfuscated)

        # Obfuscated data sections in canonical order
        for label in SECTION_ORDER:
            out.write(obfuscated_sections[label])

    total_bytes = os.path.getsize(output_path)

    if verbose:
        manifest_obj = json.loads(manifest_raw)
        print(f'\n  slug     : {slug}')
        print(f'  manifest : {manifest_size} bytes (at file offset 9)')
        for label in SECTION_ORDER:
            info = manifest_obj['sections'][label]
            print(f'  {label:8s} : offset={info["offset"]:>10,}  size={info["size"]:>10,}')
        print(f'\n  output   : {output_path}')
        print(f'  total    : {total_bytes:,} bytes  ({total_bytes / 1_000_000:.2f} MB)')

    return output_path


# ── Verification helper ───────────────────────────────────────────────────────

def verify(mlb_path: str, passphrase: str, verbose: bool = True) -> bool:
    """Read an existing .mlb file and verify its header + manifest parse cleanly.

    Does NOT decode the full data sections – just checks the manifest is valid
    and all stated section sizes add up to the file size.
    """
    key = derive_key(passphrase)

    with open(mlb_path, 'rb') as f:
        magic = f.read(4)
        if magic != MAGIC:
            print(f'ERROR: bad magic bytes {magic!r} (expected {MAGIC!r})', file=sys.stderr)
            return False

        version = ord(f.read(1))
        (manifest_size,) = struct.unpack('>I', f.read(4))

        manifest_obfuscated = f.read(manifest_size)
        if len(manifest_obfuscated) != manifest_size:
            print('ERROR: truncated manifest', file=sys.stderr)
            return False

        manifest_raw = xor_bytes(manifest_obfuscated, key)
        try:
            manifest_obj = json.loads(manifest_raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f'ERROR: manifest could not be decoded: {e}', file=sys.stderr)
            print('       (wrong passphrase?)', file=sys.stderr)
            return False

    file_size = os.path.getsize(mlb_path)
    sections = manifest_obj.get('sections', {})
    expected_data_end = 0
    for label in SECTION_ORDER:
        info = sections.get(label)
        if info is None:
            print(f'ERROR: manifest missing section "{label}"', file=sys.stderr)
            return False
        end = info['offset'] + info['size']
        expected_data_end = max(expected_data_end, end)

    if expected_data_end != file_size:
        print(
            f'ERROR: manifest says data ends at byte {expected_data_end} '
            f'but file is {file_size} bytes',
            file=sys.stderr,
        )
        return False

    if verbose:
        print(f'OK  {mlb_path}')
        print(f'    version : {version}')
        print(f'    slug    : {manifest_obj.get("slug")}')
        for label in SECTION_ORDER:
            info = sections[label]
            print(f'    {label:8s}: offset={info["offset"]:>10,}  size={info["size"]:>10,}')

    return True


# ── Batch bundling helper ─────────────────────────────────────────────────────

def find_all_lesson_folders(parent_dir: str) -> list[str]:
    """Recursively find all directories that contain lesson files (.json + .mp3s).

    Returns a sorted list of absolute paths to lesson folders.
    """
    parent_dir = os.path.abspath(parent_dir)
    lesson_folders: list[str] = []

    try:
        for entry in os.scandir(parent_dir):
            if not entry.is_dir(follow_symlinks=False):
                continue
            if entry.name.startswith('.'):
                continue

            # Check if this folder contains lesson files
            try:
                find_lesson_files(entry.path)
                lesson_folders.append(entry.path)
            except FileNotFoundError:
                # Not a complete lesson folder, skip
                pass

    except (PermissionError, OSError):
        pass

    return sorted(lesson_folders)


def batch_bundle(
    parent_dir: str,
    passphrase: str,
    output_dir: str | None = None,
    verbose: bool = True,
) -> None:
    """Bundle all lesson folders found in parent_dir (non-recursive).

    If output_dir is None, .mlb files are written alongside the source folders.
    """
    parent_dir = os.path.abspath(parent_dir)
    output_dir = os.path.abspath(output_dir) if output_dir else parent_dir

    lesson_folders = find_all_lesson_folders(parent_dir)

    if not lesson_folders:
        print(f'No lesson folders found in {parent_dir}', file=sys.stderr)
        return

    if verbose:
        print(f'Found {len(lesson_folders)} lesson folder(s) to bundle:\n')
        for folder in lesson_folders:
            print(f'  {os.path.basename(folder)}')
        print()

    os.makedirs(output_dir, exist_ok=True)
    successful: list[str] = []
    failed: list[tuple[str, str]] = []

    for lesson_folder in lesson_folders:
        try:
            slug, *_ = find_lesson_files(lesson_folder)
            output_path = os.path.join(output_dir, f'{slug}.mlb')

            if verbose:
                print(f'Bundling: {os.path.basename(lesson_folder)} → {os.path.basename(output_path)}')

            bundle(lesson_folder, output_path, passphrase, verbose=False)
            successful.append(slug)

            if verbose:
                file_size = os.path.getsize(output_path)
                print(f'  ✓ {file_size:,} bytes\n')

        except FileNotFoundError as e:
            failed.append((os.path.basename(lesson_folder), str(e)))
            if verbose:
                print(f'  ✗ Error: {e}\n')
        except Exception as e:
            failed.append((os.path.basename(lesson_folder), str(e)))
            if verbose:
                print(f'  ✗ Unexpected error: {e}\n')

    # Summary
    if verbose:
        print('─' * 60)
        print(f'Completed: {len(successful)} successful, {len(failed)} failed')
        if successful:
            print(f'\nSuccessfully bundled:')
            for slug in successful:
                print(f'  ✓ {slug}')
        if failed:
            print(f'\nFailed:')
            for name, error in failed:
                print(f'  ✗ {name}: {error}')
        print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def get_passphrase_from_args_or_env(args_key: str | None) -> str:
    """Get passphrase from args, environment variable, or raise error.

    Priority:
    1. --key argument (if provided)
    2. bundle_password environment variable
    3. Raise error
    """
    if args_key:
        return args_key

    env_key = os.environ.get('bundle_password')
    if env_key:
        return env_key

    raise ValueError(
        'No passphrase provided. Use --key argument or set bundle_password '
        'environment variable (e.g. export bundle_password="...").'
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Create or verify a Magic Learning Bundle (.mlb) file.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # ── bundle subcommand ────────────────────────────────────────────────────
    p_bundle = subparsers.add_parser(
        'bundle',
        help='Pack a lesson folder into a .mlb file.',
    )
    p_bundle.add_argument(
        '--input', '-i', required=True,
        metavar='FOLDER',
        help='Lesson folder containing <slug>.json and the three MP3 files.',
    )
    p_bundle.add_argument(
        '--output', '-o',
        metavar='FILE',
        help='Output .mlb path. Defaults to <slug>.mlb in the current directory.',
    )
    p_bundle.add_argument(
        '--key', '-k',
        metavar='PASSPHRASE',
        help='Passphrase for XOR obfuscation. If omitted, uses bundle_password env var.',
    )
    p_bundle.add_argument(
        '--quiet', '-q', action='store_true',
        help='Suppress progress output.',
    )

    # ── batch-bundle subcommand ──────────────────────────────────────────────
    p_batch = subparsers.add_parser(
        'batch-bundle',
        help='Bundle all lesson folders found in a directory.',
    )
    p_batch.add_argument(
        '--input', '-i', required=True,
        metavar='FOLDER',
        help='Parent folder containing lesson subfolders.',
    )
    p_batch.add_argument(
        '--output-dir', '-o',
        metavar='DIR',
        help='Output directory for .mlb files. Defaults to input folder.',
    )
    p_batch.add_argument(
        '--key', '-k',
        metavar='PASSPHRASE',
        help='Passphrase for XOR obfuscation. If omitted, uses bundle_password env var.',
    )
    p_batch.add_argument(
        '--quiet', '-q', action='store_true',
        help='Suppress progress output.',
    )

    # ── verify subcommand ────────────────────────────────────────────────────
    p_verify = subparsers.add_parser(
        'verify',
        help='Verify the header and manifest of an existing .mlb file.',
    )
    p_verify.add_argument(
        'file',
        metavar='FILE',
        help='.mlb file to verify.',
    )
    p_verify.add_argument(
        '--key', '-k',
        metavar='PASSPHRASE',
        help='Passphrase that was used when bundling. If omitted, uses bundle_password env var.',
    )

    args = parser.parse_args()

    # ── dispatch ─────────────────────────────────────────────────────────────
    if args.command == 'bundle':
        folder = os.path.abspath(args.input)
        if not os.path.isdir(folder):
            print(f'Error: "{folder}" is not a directory.', file=sys.stderr)
            sys.exit(1)

        verbose = not args.quiet
        if verbose:
            print(f'Bundling: {folder}\n')

        try:
            passphrase = get_passphrase_from_args_or_env(args.key)
            slug, *_ = find_lesson_files(folder)
            output_path = args.output or f'{slug}.mlb'
            bundle(folder, output_path, passphrase, verbose=verbose)
            if verbose:
                print('\nDone.')
        except FileNotFoundError as e:
            print(f'Error: {e}', file=sys.stderr)
            sys.exit(1)
        except ValueError as e:
            print(f'Error: {e}', file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f'Unexpected error: {e}', file=sys.stderr)
            sys.exit(1)

    elif args.command == 'batch-bundle':
        folder = os.path.abspath(args.input)
        if not os.path.isdir(folder):
            print(f'Error: "{folder}" is not a directory.', file=sys.stderr)
            sys.exit(1)

        verbose = not args.quiet

        try:
            passphrase = get_passphrase_from_args_or_env(args.key)
            output_dir = args.output_dir
            batch_bundle(folder, passphrase, output_dir=output_dir, verbose=verbose)
        except ValueError as e:
            print(f'Error: {e}', file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f'Unexpected error: {e}', file=sys.stderr)
            sys.exit(1)

    elif args.command == 'verify':
        try:
            passphrase = get_passphrase_from_args_or_env(args.key)
            ok = verify(args.file, passphrase)
            sys.exit(0 if ok else 1)
        except ValueError as e:
            print(f'Error: {e}', file=sys.stderr)
            sys.exit(1)



if __name__ == '__main__':
    main()
