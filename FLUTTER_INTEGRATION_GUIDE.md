# Flutter Integration Guide — Magic Learning Bundle (.mlb)

This document explains how to modify the existing Magic Learning app to load
lessons from `.mlb` bundle files instead of individual MP3 and JSON files.

Read `MLB_FORMAT_SPEC.md` first for the binary format details.

---

## Overview of Changes

There are four things to add or modify:

| # | What | File(s) to touch |
|---|------|-----------------|
| 1 | Add `crypto` package for SHA-256 key derivation | `pubspec.yaml` |
| 2 | Create `MlbReader` — opens a `.mlb` file and exposes section data | new file `lib/services/mlb_reader.dart` |
| 3 | Create `MlbStreamAudioSource` — feeds an audio section to `just_audio` without extracting to disk | new file `lib/services/mlb_audio_source.dart` |
| 4 | Update `LessonRepository` — download/store `.mlb` instead of four separate files | `lib/services/lesson_repository.dart` |
| 5 | Update `AudioSequenceService` — call `setAudioSource()` for MLB tracks instead of `setFilePath()` / `setUrl()` | `lib/services/audio_sequence_service.dart` |

---

## Step 1 — Add the `crypto` package

`crypto` is a first-party Dart package for SHA-256.  It has no native code and
adds no binary size overhead worth noting.

In `pubspec.yaml`, under `dependencies:`, add:

```yaml
dependencies:
  # ... existing entries ...
  crypto: ^3.0.3
```

Then run:

```sh
flutter pub get
```

---

## Step 2 — Create `MlbReader`

Create `lib/services/mlb_reader.dart`.

This class:
- Opens the `.mlb` file (keeps a `RandomAccessFile` handle open)
- Derives the 32-byte key from the hardcoded passphrase
- Reads and decodes the manifest on construction
- Exposes `readSection(name)` → `Uint8List` for small sections (JSON)
- Exposes `sectionOffset(name)` and `sectionSize(name)` for audio sections
  (so the audio source can stream without reading the whole section at once)

```dart
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

class MlbReader {
  // ── Public constants ──────────────────────────────────────────────────────

  /// The passphrase compiled into the app.
  /// Must match the --key argument passed to bundle_lesson.py.
  static const String _passphrase = 'YOUR_SECRET_PASSPHRASE_HERE';

  // ── State ─────────────────────────────────────────────────────────────────

  final RandomAccessFile _raf;
  final Uint8List _key;
  final Map<String, _SectionInfo> _sections;
  final String slug;

  MlbReader._({
    required RandomAccessFile raf,
    required Uint8List key,
    required Map<String, _SectionInfo> sections,
    required this.slug,
  })  : _raf = raf,
        _key = key,
        _sections = sections;

  // ── Factory constructor ───────────────────────────────────────────────────

  static Future<MlbReader> open(String filePath) async {
    final key = Uint8List.fromList(
      sha256.convert(utf8.encode(_passphrase)).bytes,
    );

    final raf = await File(filePath).open();

    // Read and validate fixed header
    final magic = await _readBytes(raf, 4);
    if (magic[0] != 0x4D || magic[1] != 0x4C ||
        magic[2] != 0x52 || magic[3] != 0x4E) {
      await raf.close();
      throw FormatException('Not a valid .mlb file: bad magic bytes');
    }

    final versionByte = (await _readBytes(raf, 1))[0];
    if (versionByte != 1) {
      await raf.close();
      throw FormatException('Unsupported .mlb format version: $versionByte');
    }

    final manifestSizeBytes = await _readBytes(raf, 4);
    final manifestSize = (manifestSizeBytes[0] << 24) |
        (manifestSizeBytes[1] << 16) |
        (manifestSizeBytes[2] << 8) |
        manifestSizeBytes[3];

    // Decode manifest
    final encodedManifest = await _readBytes(raf, manifestSize);
    final manifestJson = _xorDecode(encodedManifest, key);
    final manifest = jsonDecode(utf8.decode(manifestJson)) as Map<String, dynamic>;

    final slug = (manifest['slug'] as String?) ?? '';
    final rawSections = manifest['sections'] as Map<String, dynamic>;

    final sections = <String, _SectionInfo>{};
    for (final entry in rawSections.entries) {
      final info = entry.value as Map<String, dynamic>;
      sections[entry.key] = _SectionInfo(
        offset: (info['offset'] as num).toInt(),
        size: (info['size'] as num).toInt(),
      );
    }

    return MlbReader._(raf: raf, key: key, sections: sections, slug: slug);
  }

  // ── Public API ────────────────────────────────────────────────────────────

  /// Read and fully decode a section into memory.
  ///
  /// Use for small sections (e.g. `"json"`).
  /// For audio sections prefer [sectionOffset] + [sectionSize] with
  /// [MlbStreamAudioSource] to avoid loading megabytes into RAM.
  Future<Uint8List> readSection(String name) async {
    final info = _requireSection(name);
    await _raf.setPosition(info.offset);
    final encoded = await _readBytes(_raf, info.size);
    return _xorDecode(encoded, _key);
  }

  /// Read a range of raw (still-encoded) bytes from a section.
  ///
  /// Used internally by [MlbStreamAudioSource] to feed the audio player
  /// in chunks while decoding on the fly.
  Future<Uint8List> readSectionRange(
    String name,
    int startWithinSection,
    int length,
  ) async {
    final info = _requireSection(name);
    assert(startWithinSection >= 0);
    assert(startWithinSection + length <= info.size);

    final fileOffset = info.offset + startWithinSection;
    await _raf.setPosition(fileOffset);
    final encoded = await _readBytes(_raf, length);

    // XOR key index = startWithinSection mod 32 (because each section resets
    // to key index 0 at its own start)
    return _xorDecodeWithOffset(encoded, _key, startWithinSection);
  }

  int sectionSize(String name) => _requireSection(name).size;
  int sectionOffset(String name) => _requireSection(name).offset;

  Future<void> close() => _raf.close();

  // ── Private helpers ───────────────────────────────────────────────────────

  _SectionInfo _requireSection(String name) {
    final info = _sections[name];
    if (info == null) throw ArgumentError('Section "$name" not found in manifest');
    return info;
  }

  static Future<Uint8List> _readBytes(RandomAccessFile raf, int count) async {
    final buf = Uint8List(count);
    int read = 0;
    while (read < count) {
      final n = await raf.readInto(buf, read, count);
      if (n == 0) throw const FormatException('Unexpected end of .mlb file');
      read += n;
    }
    return buf;
  }

  static Uint8List _xorDecode(Uint8List data, Uint8List key) {
    return _xorDecodeWithOffset(data, key, 0);
  }

  static Uint8List _xorDecodeWithOffset(
    Uint8List data,
    Uint8List key,
    int keyStartIndex,
  ) {
    final result = Uint8List(data.length);
    final keyLen = key.length;
    for (int i = 0; i < data.length; i++) {
      result[i] = data[i] ^ key[(keyStartIndex + i) % keyLen];
    }
    return result;
  }
}

class _SectionInfo {
  const _SectionInfo({required this.offset, required this.size});
  final int offset;
  final int size;
}
```

> **Security note**: Replace `'YOUR_SECRET_PASSPHRASE_HERE'` with a real
> hard-to-guess string before shipping.  Keep it the same value you pass to
> `--key` in the bundler.

---

## Step 3 — Create `MlbStreamAudioSource`

Create `lib/services/mlb_audio_source.dart`.

`just_audio`'s `StreamAudioSource` API lets you provide audio bytes on demand.
The audio player calls `request(start, end)` with byte ranges as it buffers.
This class decodes exactly the requested bytes from the section, so the whole
audio file is never loaded into RAM at once.

```dart
import 'dart:typed_data';

import 'package:just_audio/just_audio.dart';

import 'mlb_reader.dart';

class MlbStreamAudioSource extends StreamAudioSource {
  MlbStreamAudioSource({
    required MlbReader reader,
    required String section,   // 'story', 'lexical', or 'drills'
  })  : _reader = reader,
        _section = section,
        _totalBytes = reader.sectionSize(section);

  final MlbReader _reader;
  final String _section;
  final int _totalBytes;

  @override
  Future<StreamAudioResponse> request([int? start, int? end]) async {
    start ??= 0;
    end ??= _totalBytes;
    final length = end - start;

    final decoded = await _reader.readSectionRange(_section, start, length);

    return StreamAudioResponse(
      sourceLength: _totalBytes,
      contentLength: length,
      offset: start,
      contentType: 'audio/mpeg',
      stream: Stream.value(decoded),
    );
  }
}
```

This is intentionally minimal — `just_audio` handles all the caching and
re-requesting internally once you hand it a `StreamAudioSource`.

---

## Step 4 — Update `LessonRepository`

The repository needs to:
- Download one `.mlb` file per lesson instead of four separate files
- Know whether a local `.mlb` bundle already exists
- Open an `MlbReader` for a lesson on demand

### 4a — Bundle file path helper

Add a private method:

```dart
Future<File> _mlbFileFor(LessonCatalogItem lesson) async {
  final lessonDir = await _lessonDirectoryFor(lesson);
  return File('${lessonDir.path}/${lesson.slug}.mlb');
}
```

### 4b — Check for complete local bundle

Replace (or supplement) `_hasCompleteLocalBundle` to check for the `.mlb` file:

```dart
Future<bool> _hasCompleteLocalBundle(LessonCatalogItem lesson) async {
  final mlb = await _mlbFileFor(lesson);
  return mlb.exists();
}
```

> If you want to support both the old (four separate files) format and the new
> `.mlb` format during a transition period, check for both and return `true`
> if either is complete.

### 4c — Download the bundle

Replace `_downloadLessonBundleInternal` to download the single `.mlb` file:

```dart
Future<void> _downloadLessonBundleInternal(LessonCatalogItem lesson) async {
  _downloadingLessonIds.add(lesson.id);
  notifyListeners();

  try {
    final mlbUrl = '${_normalizeBaseUrl(lesson.baseUrl)}${lesson.slug}.mlb';
    final mlbFile = await _mlbFileFor(lesson);

    final response = await _httpClient.get(Uri.parse(mlbUrl));
    if (response.statusCode != 200) {
      throw Exception('Failed to download .mlb: HTTP ${response.statusCode}');
    }

    await mlbFile.writeAsBytes(response.bodyBytes);
    await _markLessonDownloaded(lesson);
  } finally {
    _downloadingLessonIds.remove(lesson.id);
    notifyListeners();
  }
}
```

> For large files (18 MB+) prefer a streaming download using `http.Client.send`
> with `StreamedRequest` instead of `http.Client.get` to avoid loading the
> entire bundle into memory before writing it.  The example above is simplified
> for clarity.

### 4d — Expose an MlbReader to the service layer

Add a method that the audio service can call:

```dart
Future<MlbReader?> openMlbReader(LessonCatalogItem lesson) async {
  final mlb = await _mlbFileFor(lesson);
  if (!await mlb.exists()) return null;
  return MlbReader.open(mlb.path);
}
```

### 4e — Keep `fetchStoryDataForLesson` working

The JSON data is now inside the `.mlb`, so `_readLocalStoryData` must be
updated to extract it from there:

```dart
Future<StoryData?> _readLocalStoryData(LessonCatalogItem lesson) async {
  final reader = await openMlbReader(lesson);
  if (reader == null) return null;
  try {
    final jsonBytes = await reader.readSection('json');
    final decoded = jsonDecode(utf8.decode(jsonBytes)) as Map<String, dynamic>;
    return StoryData.fromJson(decoded);
  } finally {
    await reader.close();
  }
}
```

---

## Step 5 — Update `AudioSequenceService`

### 5a — Add an `MlbReader` cache field

Inside `AudioSequenceService`, hold onto a reader that is opened once per
loaded lesson and closed when the lesson changes:

```dart
MlbReader? _mlbReader;

Future<void> _closeMlbReader() async {
  await _mlbReader?.close();
  _mlbReader = null;
}
```

Call `_closeMlbReader()` anywhere the lesson is cleared or replaced (e.g. in
`clearLesson()` and at the beginning of `prepareLesson()`).

### 5b — Open the reader when the lesson is prepared

In `prepareLesson()` (or wherever `_selectedLessonMeta` is set), after the
lesson bundle is ensured offline, open the reader:

```dart
await _closeMlbReader();
_mlbReader = await _repository?.openMlbReader(lesson);
```

### 5c — Replace `_ensureAudioTrackLoaded`

This is the key change.  The existing method resolves a file path or URL and
calls `setFilePath` / `setUrl`.  Replace it with a branch that uses the MLB
reader when available:

```dart
Future<bool> _ensureAudioTrackLoaded(_AudioTrack track) async {
  final lesson = _selectedLessonMeta;
  final repo = _repository;
  if (lesson == null || repo == null) return false;
  if (_loadedTrack == track) return true;

  try {
    // ── MLB path (preferred when bundle is downloaded) ──────────────────
    final reader = _mlbReader;
    if (reader != null) {
      final sectionName = _sectionNameForTrack(track);   // see 5d below
      final source = MlbStreamAudioSource(
        reader: reader,
        section: sectionName,
      );
      await _player.setAudioSource(source);
      await _player.setSpeed(_speed);
      _loadedTrack = track;
      notifyListeners();
      return true;
    }

    // ── Fallback: individual file path or remote URL ────────────────────
    final fileName = _audioFileNameForTrack(lesson, track);
    final path = await repo.resolveAudioPath(lesson, fileName);

    if (path.startsWith('/') || path.startsWith('file://')) {
      await _player.setFilePath(
        path.startsWith('file://') ? Uri.parse(path).toFilePath() : path,
      );
    } else {
      await _player.setUrl(path);
    }

    await _player.setSpeed(_speed);
    _loadedTrack = track;
    notifyListeners();
    return true;
  } catch (e) {
    _lastError = 'Could not load ${track.name} audio: $e';
    _phase = PlaybackPhase.stopped;
    notifyListeners();
    return false;
  }
}
```

### 5d — Map `_AudioTrack` to section names

Add a tiny helper (or a switch expression):

```dart
String _sectionNameForTrack(_AudioTrack track) => switch (track) {
  _AudioTrack.story   => 'story',
  _AudioTrack.lexical => 'lexical',
  _AudioTrack.drills  => 'drills',
};
```

---

## MlbReader Lifecycle Summary

```
prepareLesson()
  └─ await _closeMlbReader()
  └─ await repo.ensureLessonAvailableOffline(lesson)
  └─ _mlbReader = await repo.openMlbReader(lesson)   ← file is now open

_ensureAudioTrackLoaded(track)
  └─ MlbStreamAudioSource(reader: _mlbReader, section: ...)
  └─ _player.setAudioSource(source)                  ← player reads on demand

clearLesson() / dispose()
  └─ await _closeMlbReader()                          ← file is closed
```

The `RandomAccessFile` inside `MlbReader` stays open for the lifetime of the
loaded lesson.  It is safe because:
- Only one lesson is loaded at a time.
- The file handle is explicitly closed when the lesson changes.
- Mobile OSes allow hundreds of concurrent open file handles.

---

## Transition Strategy (old files → .mlb)

While you are switching over, you can keep backward compatibility:

1. In `_hasCompleteLocalBundle`, check for `.mlb` first, then fall back to the
   four individual files.
2. In `_ensureAudioTrackLoaded`, check `_mlbReader != null` first (MLB path),
   then fall back to the existing `resolveAudioPath` logic.
3. Old downloaded lessons continue to work without re-downloading.
4. New downloads always download the `.mlb`.
5. Once all users have migrated (or after a forced app update), remove the
   four-file fallback paths.

---

## What Does NOT Change

- `StoryData`, `LessonCatalogItem`, and all models — unchanged.
- All mode playback logic (story virtual timeline, Q&A stages, delays) — unchanged.
- Progress bar, seek scrubbing, speed/delay settings — unchanged.
- The catalog (`catalog.json`) on GitHub — unchanged.
- How remote lessons load before they are downloaded — unchanged (still uses
  `resolveAudioPath` → remote URL path).

---

## Caveats and Known Limitations

| Concern | Notes |
|---|---|
| Reverse-engineering | A motivated attacker with the APK/IPA can extract the passphrase from the compiled binary.  This protects against casual scraping, not professional piracy. |
| Streaming large downloads | The simplified download in Step 4c loads the full response into memory.  For production, pipe the HTTP response stream directly to disk. |
| Seek performance | `RandomAccessFile.setPosition()` is fast on mobile; the seek-per-request pattern in `MlbStreamAudioSource` should not cause audible gaps during normal playback buffering. |
| Concurrent track loads | `MlbReader` uses a single `RandomAccessFile`.  If story and drills are ever loaded simultaneously, add a `Mutex` (from the `synchronized` package) around `setPosition` + `readInto` calls. |
