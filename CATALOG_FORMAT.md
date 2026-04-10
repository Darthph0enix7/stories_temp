# Catalog.json Format Documentation

## Overview
`catalog.json` is an indexed catalog that aggregates metadata from all story sources (folders and .mlb bundles), enabling fast querying and listing of available stories in your app without parsing individual story files or bundles.

## Data Sources

The catalog automatically indexes stories from:
1. **Folder-based stories** — legacy format with `<slug>.json` + three MP3 files
2. **.mlb bundles** — modern format with all assets packed into a single binary file

When both formats exist for the same story, the **.mlb bundle takes precedence**.

## Structure

### Root Object
```json
{
  "meta": { ... },
  "stories": [ ... ]
}
```

### Meta Section
Metadata about the catalog itself:

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Catalog format version (semver: "1.0") |
| `generated` | string | ISO 8601 timestamp of last generation |
| `total` | number | Total count of stories in catalog |
| `description` | string | Brief description of the catalog |

**Example:**
```json
"meta": {
  "version": "1.0",
  "generated": "2026-04-09T21:44:36.682779",
  "total": 10,
  "description": "Indexed catalog of stories with metadata"
}
```

### Stories Array
Array of story objects. Each story contains:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier (folder name, slug-format for URLs) |
| `title` | string | Display title of the story |
| `level` | string | CEFR level (A1, A2, B1, B2, etc.) |
| `duration` | number | Total duration in seconds (from last sentence timing) |
| `hasAudio` | object | Availability of audio/MP3 files |
| `hasAudio.story` | boolean | Story narration file exists |
| `hasAudio.drills` | boolean | Drills audio file exists |
| `hasAudio.lexical` | boolean | Lexical audio file exists |
| `source` | string | Data source: `"mlb"` (bundle) or `"folder"` |

**Example Story Entry (from .mlb bundle):**
```json
{
  "id": "balus-essen-a2",
  "title": "Balus Essen",
  "level": "A2",
  "duration": 105.46,
  "hasAudio": {
    "story": true,
    "drills": true,
    "lexical": true
  },
  "source": "mlb"
}
```

**Example Story Entry (from folder):**
```json
{
  "id": "das-licht-des-leuchtturms-a2",
  "title": "Das Licht des Leuchtturms",
  "level": "A2",
  "duration": 54.67,
  "hasAudio": {
    "story": true,
    "drills": false,
    "lexical": true
  },
  "source": "folder"
}
```

## Usage Examples

### Listing all stories by level
```javascript
const catalog = require('./catalog.json');
const a2Stories = catalog.stories.filter(s => s.level === 'A2');
```

### Filtering by available audio
```javascript
const withFullAudio = catalog.stories.filter(s => 
  s.hasAudio.story && s.hasAudio.drills && s.hasAudio.lexical
);
```

### Quick metadata access
```javascript
const story = catalog.stories.find(s => s.id === 'veraendert-a2');
console.log(`${story.title} - ${story.duration}s - ${story.wordCount} words`);
```

## Current Contents (10 stories)

| Title | Level | Duration | Source | Audio |
|-------|-------|----------|--------|-------|
| Balus Essen | A2 | 105s | mlb | ✓ |
| Bilderrätsel: Das geheime Erbe | A2 | 74s | mlb | ✓ |
| Bunter Markt mit Gewürzen | A2 | 85s | mlb | ✓ |
| Das Geheimnis der Bibliothek | A2 | 88s | mlb | ✓ |
| Das Licht des Leuchtturms | A2 | 55s | mlb | ✓ |
| Der Fußball-Hase | A2 | 132s | mlb | ✓ |
| Ein Kuss | A2 | 92s | mlb | ✓ |
| Tag der Toten | A2 | 104s | mlb | ✓ |
| Verändert | A2 | 51s | mlb | ✓ |
| Verändert | B1 | 49s | mlb | ✓ |

## Updating the Catalog

When adding new stories, you can use either approach:

**Option 1: Add folder with JSON + 3 MP3 files**
```
new-story-a2/
  ├── new-story-a2.json
  ├── new-story-a2-story.mp3
  ├── new-story-a2-drills.mp3
  └── new-story-a2-lexical.mp3
```

**Option 2: Add .mlb bundle file**
```
new-story-a2.mlb    (contains all assets, XOR-obfuscated)
```

Then regenerate the catalog:
```bash
python3 generate_catalog.py
```

### How the script works:

1. Scans for all `.mlb` bundles in the base directory
2. Decodes each manifest and extracts title, level, duration
3. Scans for folder-based stories
4. Merges results (bundles take precedence if both formats exist for same story)
5. Regenerates `catalog.json` with updated timestamp

### Implementation details:

- **MLB Reader**: Imports `MAGIC`, `FORMAT_VERSION`, and XOR utilities from `bundle_lesson.py` format spec
- **Key**: Uses hardcoded passphrase `"Denemeler123."` (from environment setup)
- **Precedence**: If both `slug.mlb` and `slug/` exist, the bundle is used
- **Sorting**: Final catalog sorted by level, then by title (alphabetical)
