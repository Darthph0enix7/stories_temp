# Magic Learning Bundle Setup Complete ✓

## Environment Variable Set ✓

The `bundle_password` environment variable has been set globally:

```bash
bundle_password="Denemeler123."
```

**Location:** `~/.config/fish/config.fish` (persists across all sessions)

### Verify it's set:
```bash
echo $bundle_password
```

## Modified Script Features

The `bundle_lesson.py` script has been enhanced with three main features:

### 1. **Single Lesson Bundling** (with optional key)
Bundle a single lesson folder:

```bash
# Using environment variable (default)
python3 bundle_lesson.py bundle --input ./das-licht-des-leuchtturms-a2

# Or with explicit key
python3 bundle_lesson.py bundle --input ./das-licht-des-leuchtturms-a2 --key Denemeler123.
```

**Output:** `das-licht-des-leuchtturms-a2.mlb` (in current directory or `--output` path)

### 2. **Batch Bundling All Lessons** ⭐ (NEW)
Bundle ALL lesson folders at once:

```bash
# Bundle all lessons in current directory (uses environment variable)
python3 bundle_lesson.py batch-bundle --input .

# Or specify a custom output directory
python3 bundle_lesson.py batch-bundle --input . --output-dir ./bundles
```

**Output:** All `.mlb` files in the target directory

### 3. **Verify Bundle Integrity**
Verify that a bundle file is valid:

```bash
# Using environment variable (default)
python3 bundle_lesson.py verify das-licht-des-leuchtturms-a2.mlb

# Or with explicit key
python3 bundle_lesson.py verify das-licht-des-leuchtturms-a2.mlb --key Denemeler123.
```

---

## Test Results ✓

Successfully bundled all 10 lessons:

| Lesson | File Size |
|--------|-----------|
| balus-essen-a2 | 1.3 MB |
| bilderratsel-das-geheime-erbe-a2 | 18 MB |
| bunter-markt-mit-gewurzen-a2 | 24 MB |
| das-geheimnis-der-bibliothek-a2 | 21 MB |
| das-licht-des-leuchtturms-a2 | 17 MB |
| der-fussball-hase-a2 | 26 MB |
| ein-kuss-a2 | 20 MB |
| tag-der-toten-a2 | 24 MB |
| veraendert-a2 | 16 MB |
| veraendert-b1 | 14 MB |
| **Total** | **~191 MB** |

### Verification Test:
```
✓ das-licht-des-leuchtturms-a2.mlb verified successfully
  - Version: 1
  - JSON: 55,786 bytes
  - Story MP3: 656,396 bytes
  - Lexical MP3: 9,409,004 bytes
  - Drills MP3: 8,011,916 bytes
```

---

## What Changed in bundle_lesson.py

### New Functions:
- **`find_all_lesson_folders(parent_dir)`** - Recursively finds all lesson folders
- **`batch_bundle(...)`** - Bundles all lessons in a directory with progress reporting
- **`get_passphrase_from_args_or_env(...)`** - Gets passphrase from args or environment variable

### New Subcommand:
- **`batch-bundle`** - Bundle all lessons at once with summary reporting

### Key Arguments:
- `--key` / `-k` - Now **optional** (falls back to `bundle_password` env var)
- `--output-dir` / `-o` - New option for `batch-bundle` to specify output location

### Help:
```bash
python3 bundle_lesson.py --help          # Show all commands
python3 bundle_lesson.py bundle --help   # Single bundle help
python3 bundle_lesson.py batch-bundle --help  # Batch bundle help
python3 bundle_lesson.py verify --help   # Verify help
```

---

## Usage Examples

### Quick Start (using environment variable):
```bash
# One command to bundle everything
cd ~/Main_Base/tmp
python3 bundle_lesson.py batch-bundle --input .
```

### With Progress (all bundled, one-by-one display):
```bash
python3 bundle_lesson.py batch-bundle --input . --verbose
```

### Save bundles to specific folder:
```bash
python3 bundle_lesson.py batch-bundle --input . --output-dir ~/bundles
```

### In a script (add to cron, CI/CD, etc.):
```bash
#!/bin/bash
source ~/.config/fish/config.fish
cd ~/Main_Base/tmp
python3 bundle_lesson.py batch-bundle --input . --quiet
echo "Bundling complete!"
```

---

## Format Details

Each `.mlb` bundle contains:
- ✓ JSON lesson data (metadata, vocabulary, content)
- ✓ Story MP3 audio file
- ✓ Lexical MP3 audio file  
- ✓ Drills MP3 audio file

All data is XOR-obfuscated using SHA-256(passphrase) as the key.

See `MLB_FORMAT_SPEC.md` for full technical details.

---

## Next Steps

The `.mlb` files are now ready to be:
1. ✓ Uploaded to your server for downloading in the Flutter app
2. ✓ Integrated with Flutter using `MlbReader` (see `FLUTTER_INTEGRATION_GUIDE.md`)
3. ✓ Verified using the `verify` command before deployment

All bundles use the same passphrase and will work seamlessly with the Flutter integration.
