#!/usr/bin/env python3
"""
Generate catalog.json from story folders and .mlb bundles
Scans all story folders and .mlb files, extracts metadata, and creates an indexed catalog
"""

import hashlib
import itertools
import json
import os
import struct
from pathlib import Path
from datetime import datetime

# MLB constants and utilities
MAGIC = b'MLRN'
FORMAT_VERSION = 1
SECTION_ORDER = ['json', 'story', 'lexical', 'drills']
PASSPHRASE = "Denemeler123."

def derive_key(passphrase: str) -> bytes:
    """Derive a 32-byte XOR key from passphrase via SHA-256"""
    return hashlib.sha256(passphrase.encode('utf-8')).digest()

def xor_bytes(data: bytes, key: bytes) -> bytes:
    """XOR every byte of data with the cycling key"""
    return bytes(b ^ k for b, k in zip(data, itertools.cycle(key)))

def read_mlb_manifest(mlb_path: str, passphrase: str) -> dict:
    """Read and decode an .mlb file's manifest"""
    key = derive_key(passphrase)
    
    with open(mlb_path, 'rb') as f:
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError(f"Invalid MLB file: bad magic bytes")
        
        version = ord(f.read(1))
        if version != FORMAT_VERSION:
            raise ValueError(f"Unsupported MLB version: {version}")
        
        (manifest_size,) = struct.unpack('>I', f.read(4))
        manifest_obfuscated = f.read(manifest_size)
        
        if len(manifest_obfuscated) != manifest_size:
            raise ValueError("Truncated manifest")
        
        manifest_json = xor_bytes(manifest_obfuscated, key)
        return json.loads(manifest_json.decode('utf-8'))

def read_mlb_json_section(mlb_path: str, manifest: dict, passphrase: str) -> dict:
    """Read and decode the JSON data section from an .mlb file"""
    key = derive_key(passphrase)
    
    sections = manifest.get('sections', {})
    json_info = sections.get('json')
    if not json_info:
        raise ValueError("Manifest missing JSON section info")
    
    offset = json_info['offset']
    size = json_info['size']
    
    with open(mlb_path, 'rb') as f:
        f.seek(offset)
        json_data_obfuscated = f.read(size)
        json_data = xor_bytes(json_data_obfuscated, key)
        return json.loads(json_data.decode('utf-8'))

def get_story_from_mlb(mlb_path: str, passphrase: str) -> dict:
    """Extract metadata from an .mlb bundle file"""
    try:
        manifest = read_mlb_manifest(mlb_path, passphrase)
        json_data = read_mlb_json_section(mlb_path, manifest, passphrase)
        
        slug = manifest.get('slug', Path(mlb_path).stem)
        title = json_data.get('title', slug)
        level = json_data.get('level', 'Unknown')
        
        # All .mlb files have all three audio sections by design
        has_audio = {
            'story': True,
            'drills': True,
            'lexical': True
        }
        
        # Extract duration from sentences if available
        sentences = json_data.get('sentences', [])
        duration = sentences[-1].get('sentence-end', 0) if sentences else 0
        
        return {
            'slug': slug,
            'title': title,
            'level': level,
            'duration': round(duration, 2),
            'hasAudio': has_audio,
            'source': 'mlb'
        }
    except Exception as e:
        print(f"✗ Error reading {mlb_path}: {e}")
        return None

def get_duration_from_story(story_data):
    """Extract total duration from sentences array (last sentence-end)"""
    sentences = story_data.get("sentences", [])
    if sentences:
        return sentences[-1].get("sentence-end", 0)
    return 0

def check_story_files(folder_path, base_name):
    """Check which audio files (mp3) exist"""
    files = {
        "story": os.path.exists(os.path.join(folder_path, f"{base_name}-story.mp3")),
        "drills": os.path.exists(os.path.join(folder_path, f"{base_name}-drills.mp3")),
        "lexical": os.path.exists(os.path.join(folder_path, f"{base_name}-lexical.mp3"))
    }
    return files

def generate_catalog():
    """Main function to generate catalog from both folders and .mlb bundles"""
    base_path = Path("/Users/dartphoenix_mac/Main_Base/tmp")
    stories_dict = {}  # Use dict keyed by slug to handle duplicates
    
    # ─── Scan for .mlb bundle files ───
    print("Scanning for .mlb bundles...")
    for mlb_file in sorted(base_path.glob("*.mlb")):
        story_data = get_story_from_mlb(str(mlb_file), PASSPHRASE)
        if story_data:
            slug = story_data['slug']
            # Add or update entry (bundles take precedence if both exist)
            if slug not in stories_dict or story_data['source'] == 'mlb':
                stories_dict[slug] = {
                    "id": slug,
                    "title": story_data['title'],
                    "level": story_data['level'],
                    "duration": story_data['duration'],
                    "hasAudio": story_data['hasAudio'],
                    "source": story_data['source']
                }
                print(f"✓ Added: {story_data['title']} ({story_data['level']}) from bundle - {story_data['duration']:.0f}s")
    
    # ─── Scan for folder-based stories ───
    print("\nScanning for story folders...")
    story_folders = sorted([d for d in os.listdir(base_path) 
                           if os.path.isdir(os.path.join(base_path, d)) 
                           and not d.startswith('.')])
    
    for folder in story_folders:
        folder_path = base_path / folder
        json_file = folder_path / f"{folder}.json"
        
        # Skip if no JSON file found
        if not json_file.exists():
            print(f"⚠️  Skipping {folder}: No JSON file found")
            continue
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                story_data = json.load(f)
            
            title = story_data.get("title", folder)
            level = story_data.get("level", "Unknown")
            duration = get_duration_from_story(story_data)
            has_files = check_story_files(folder_path, folder)
            
            # Only add folder-based story if no bundle exists for this slug
            if folder not in stories_dict:
                stories_dict[folder] = {
                    "id": folder,
                    "title": title,
                    "level": level,
                    "duration": round(duration, 2),
                    "hasAudio": has_files,
                    "source": "folder"
                }
                print(f"✓ Added: {title} ({level}) from folder - {duration:.0f}s")
            else:
                print(f"⊘ Skipped: {title} ({level}) - using bundle version instead")
            
        except Exception as e:
            print(f"✗ Error processing {folder}: {e}")
            continue
    
    # Convert dict to sorted list
    stories = sorted(stories_dict.values(), key=lambda s: (s['level'], s['title']))
    
    # Create catalog structure
    catalog = {
        "meta": {
            "version": "1.0",
            "generated": datetime.now().isoformat(),
            "total": len(stories),
            "description": "Indexed catalog of stories with metadata (folders and bundles)"
        },
        "stories": stories
    }
    
    # Write catalog.json
    output_path = base_path / "catalog.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Catalog generated: {output_path}")
    print(f"Total stories: {len(stories)}")
    
    # Summary by source
    from_bundles = sum(1 for s in stories if stories_dict.get(s['id'], {}).get('source') == 'mlb')
    from_folders = len(stories) - from_bundles
    print(f"  - From bundles (.mlb): {from_bundles}")
    print(f"  - From folders: {from_folders}")
    
    return catalog

if __name__ == "__main__":
    generate_catalog()
