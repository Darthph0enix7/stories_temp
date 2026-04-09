# Catalog.json Format Documentation

## Overview
`catalog.json` is an indexed catalog that aggregates metadata from all story files, enabling fast querying and listing of available stories in your app without parsing individual story files.

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

**Example Story Entry:**
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
  }
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

| Title | Level | Duration | Audio |
|-------|-------|----------|-------|
| Balus Essen | A2 | 105s | ✓ |
| Bilderrätsel: Das geheime Erbe | A2 | 74s | ✓ |
| Bunter Markt mit Gewürzen | A2 | 85s | ✓ |
| Das Geheimnis der Bibliothek | A2 | 88s | ✓ |
| Das Licht des Leuchtturms | A2 | 55s | ✓ |
| Der Fußball-Hase | A2 | 132s | ✓ |
| Ein Kuss | A2 | 92s | ✓ |
| Tag der Toten | A2 | 104s | ✓ |
| Verändert | A2 | 51s | ✓ |
| Verändert | B1 | 49s | ✓ |

## Updating the Catalog

When adding new stories:

1. Add the story folder with its `{folder-name}.json` file
2. Run: `python3 generate_catalog.py`
3. Catalog auto-updates with new story metadata

The script:
- Scans all folders in `/tmp/`
- Extracts title, level from story JSON
- Calculates duration from sentence timings
- Checks for MP3 file existence (story, drills, lexical)
- Regenerates `catalog.json` with updated timestamp
