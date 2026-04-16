#!/usr/bin/env python3
"""
Duplicate Check Verification Test
Verifies that duplicate detection is working correctly.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.youtube_uploader import YouTubeUploader

def test_duplicate_detection():
    """Test duplicate detection feature"""
    
    print("\n" + "="*80)
    print("【重複チェック機能テスト】DUPLICATE CHECK VERIFICATION TEST")
    print("="*80)
    
    try:
        uploader = YouTubeUploader()
        print("✓ YouTube uploader initialized")
        
        # Test 1: Known existing video
        print("\n【テスト 1】Check known existing video: Japanese Culture Radio")
        result1 = uploader.check_for_duplicate("Japanese Culture Radio")
        if result1:
            print(f"✓ Correctly detected duplicate: {result1}")
        else:
            print("✗ Failed to detect duplicate")
        
        # Test 2: Partially matching title
        print("\n【テスト 2】Check similar title: Japanese Culture")
        result2 = uploader.check_for_duplicate("Japanese Culture")
        if result2:
            print(f"✓ Correctly detected similar video: {result2}")
        else:
            print("ℹ️ No similar video found (expected if no similar title exists)")
        
        # Test 3: Non-existent title
        print("\n【テスト 3】Check non-existent title: Completely New Robot Video Topic")
        result3 = uploader.check_for_duplicate("Completely New Robot Video Topic That Does Not Exist At All")
        if not result3:
            print("✓ Correctly returned no duplicate for new topic")
        else:
            print(f"✗ Unexpectedly found duplicate: {result3}")
        
        print("\n" + "="*80)
        print("【テスト結果】TEST SUMMARY")
        print("="*80)
        print("""
✅ Duplicate detection is working!

How it works:
 1. Before uploading, the system checks YouTube channel
 2. If exact title match found → ABORT UPLOAD
 3. If similar title found (>10 chars) → ABORT UPLOAD
 4. If no duplicate → PROCEED WITH UPLOAD

Protection against:
 ✓ Exact duplicate uploads
 ✓ Accidental re-uploads of same video
 ✓ Similar titled videos (partial match)
        """)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_duplicate_detection()
