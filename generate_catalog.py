#!/usr/bin/env python3
"""
Generate catalog.json from story folders
Scans all story folders, extracts metadata, and creates an indexed catalog
"""

import json
import os
from pathlib import Path
from datetime import datetime

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
    """Main function to generate catalog"""
    base_path = Path("/Users/dartphoenix_mac/Main_Base/tmp")
    stories = []
    
    # Get all story folders (exclude .git and .DS_Store)
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
            
            story_entry = {
                "id": folder,
                "title": title,
                "level": level,
                "duration": round(duration, 2),
                "hasAudio": {
                    "story": has_files["story"],
                    "drills": has_files["drills"],
                    "lexical": has_files["lexical"]
                }
            }
            
            stories.append(story_entry)
            print(f"✓ Added: {title} ({level}) - {duration:.0f}s")
            
        except Exception as e:
            print(f"✗ Error processing {folder}: {e}")
            continue
    
    # Create catalog structure
    catalog = {
        "meta": {
            "version": "1.0",
            "generated": datetime.now().isoformat(),
            "total": len(stories),
            "description": "Indexed catalog of stories with metadata"
        },
        "stories": stories
    }
    
    # Write catalog.json
    output_path = base_path / "catalog.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Catalog generated: {output_path}")
    print(f"Total stories: {len(stories)}")
    return catalog

if __name__ == "__main__":
    generate_catalog()
