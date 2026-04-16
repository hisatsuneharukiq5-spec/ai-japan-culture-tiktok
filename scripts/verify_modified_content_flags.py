#!/usr/bin/env python3
"""
Verify that all video upload pipelines have the required Modified Content flags.
"""

import os
from pathlib import Path

UPLOAD_FILES_TO_CHECK = [
    "src/youtube_uploader.py",
    "src/obscura_pipeline.py",
    "src/obscura_shorts_generator.py",
    "facts_scheduler.py",
]

REQUIRED_FLAGS = [
    ("selfDeclaredAsModifiedContent", True),
    ("containsSyntheticMedia", True),
]

def check_file_for_flags(file_path: str) -> dict:
    """Check if a file contains the required flags."""
    if not os.path.exists(file_path):
        return {
            "file": file_path,
            "exists": False,
            "status": "❌ FILE NOT FOUND"
        }
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    results = {
        "file": file_path,
        "exists": True,
        "flags_found": {}
    }
    
    for flag_name, expected_value in REQUIRED_FLAGS:
        # Look for the flag assignment
        search_string = f'"{flag_name}": {expected_value}'
        if search_string in content:
            results["flags_found"][flag_name] = {
                "found": True,
                "value": expected_value,
                "status": "✅"
            }
        else:
            results["flags_found"][flag_name] = {
                "found": False,
                "expected": expected_value,
                "status": "❌ MISSING"
            }
    
    # Calculate overall status
    all_found = all(f["found"] for f in results["flags_found"].values())
    results["status"] = "✅ COMPLETE" if all_found else "⚠️ INCOMPLETE"
    
    return results

def main():
    print("\n" + "="*80)
    print("🔍 VERIFICATION: Modified Content Flags in All Upload Pipelines")
    print("="*80)
    print("\nChecking that all videos are marked as:")
    print("  • Modified Content: ✅ (selfDeclaredAsModifiedContent: True)")
    print("  • Synthetic Media: ✅ (containsSyntheticMedia: True)")
    
    print("\n" + "="*80)
    print("VERIFICATION RESULTS")
    print("="*80)
    
    all_complete = True
    
    for file_path in UPLOAD_FILES_TO_CHECK:
        result = check_file_for_flags(file_path)
        
        if not result["exists"]:
            print(f"\n{file_path}")
            print(f"  Status: {result['status']}")
            all_complete = False
            continue
        
        print(f"\n{file_path}")
        print(f"  Status: {result['status']}")
        
        for flag_name, flag_result in result["flags_found"].items():
            symbol = flag_result["status"]
            value = flag_result.get("value", "NOT FOUND")
            print(f"    {symbol} {flag_name}: {value}")
        
        if result["status"] == "⚠️ INCOMPLETE":
            all_complete = False
    
    # Summary
    print("\n" + "="*80)
    if all_complete:
        print("✅ ALL PIPELINES COMPLIANT")
        print("\nSummary:")
        print("  ✓ All video uploads include Modified Content disclosure")
        print("  ✓ All video uploads include Synthetic Media disclosure")
        print("  ✓ Compliant with YouTube AI-generated content policy")
        print("  ✓ Transparent disclosure to all viewers")
    else:
        print("⚠️ SOME PIPELINES MAY BE INCOMPLETE")
        print("\nAction Required:")
        print("  1. Check each file flagged as incomplete")
        print("  2. Add missing flags to status object in YouTube video body")
        print("  3. Ensure both flags are set to True")
        print("  4. Retest all upload pipelines")
    
    print("\n" + "="*80)
    print("📋 POLICY REMINDER")
    print("="*80)
    print("""
All videos must disclose that they contain:
  • AI-generated narration (TTS: edge-tts)
  • AI-edited content (edited clips, transitions)
  • Synthetically generated elements (possible)

These flags inform viewers that content uses AI technologies,
maintaining transparency and compliance with YouTube policies.
""")
    
    return 0 if all_complete else 1

if __name__ == "__main__":
    exit(main())
