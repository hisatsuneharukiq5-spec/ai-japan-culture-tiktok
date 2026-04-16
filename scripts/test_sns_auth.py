#!/usr/bin/env python3
"""
Test script to verify TikTok and Instagram API connectivity.
Run this before using SNS posting features.
"""

import os
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from src.utils import setup_logger

logger = setup_logger("sns_auth_test")


def test_tiktok_auth():
    """Test TikTok API connection."""
    print("\n" + "=" * 70)
    print("🎵 TIKTOK API TEST")
    print("=" * 70)
    
    try:
        from src.tiktok_reels_uploader import TikTokReelsUploader, TikTokAuthHelper
        
        # Check environment variables
        client_key = os.getenv("TIKTOK_CLIENT_KEY")
        client_secret = os.getenv("TIKTOK_CLIENT_SECRET")
        access_token = os.getenv("TIKTOK_ACCESS_TOKEN")
        
        if not client_key:
            print("❌ TIKTOK_CLIENT_KEY not set in .env")
            return False
        if not client_secret:
            print("❌ TIKTOK_CLIENT_SECRET not set in .env")
            return False
        if not access_token:
            print("⚠️  TIKTOK_ACCESS_TOKEN not set")
            print("   Follow these steps:")
            print("   1. Visit SNS_API_SETUP_GUIDE.md")
            print("   2. Get authorization URL from TikTokAuthHelper")
            print("   3. Exchange code for token")
            print("   4. Add TIKTOK_ACCESS_TOKEN to .env")
            return False
        
        print(f"✓ Client Key: {client_key[:20]}...")
        print(f"✓ Client Secret: {client_secret[:20]}...")
        print(f"✓ Access Token: {access_token[:20]}...")
        
        # Try to create uploader (this validates token)
        uploader = TikTokReelsUploader()
        print("✅ TikTok API configuration valid!")
        
        return True
        
    except Exception as e:
        print(f"❌ TikTok test failed: {e}")
        return False


def test_instagram_auth():
    """Test Instagram Graph API connection."""
    print("\n" + "=" * 70)
    print("📸 INSTAGRAM REELS API TEST")
    print("=" * 70)
    
    try:
        from src.instagram_reels_uploader import InstagramReelsUploader
        
        # Check environment variables
        ig_business_id = os.getenv("INSTAGRAM_BUSINESS_ID")
        access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
        
        if not ig_business_id:
            print("❌ INSTAGRAM_BUSINESS_ID not set in .env")
            return False
        if not access_token:
            print("❌ INSTAGRAM_ACCESS_TOKEN not set in .env")
            return False
        
        print(f"✓ Business ID: {ig_business_id}")
        print(f"✓ Access Token: {access_token[:20]}...")
        
        # Try to create uploader and verify token
        uploader = InstagramReelsUploader()
        
        print("\\n🔍 Verifying token with Instagram API...")
        if uploader.verify_token():
            print("✅ Instagram API configuration valid!")
            return True
        else:
            print("❌ Token verification failed")
            return False
        
    except Exception as e:
        print(f"❌ Instagram test failed: {e}")
        return False


def test_short_video_generation():
    """Test short video generation capabilities."""
    print("\n" + "=" * 70)
    print("🎬 SHORT VIDEO GENERATION TEST")
    print("=" * 70)
    
    try:
        # Check required packages
        print("\\n📦 Checking dependencies...")
        
        import edge_tts
        print("✓ edge-tts")
        
        import requests
        print("✓ requests")
        
        import imageio_ffmpeg
        print("✓ imageio_ffmpeg")
        
        # Check Pexels API
        pexels_key = os.getenv("PEXELS_API_KEY")
        if pexels_key:
            # Test Pexels connectivity
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": pexels_key},
                params={"query": "japan", "per_page": 1},
                timeout=10
            )
            if resp.status_code == 200:
                print("✓ Pexels API connectivity")
            else:
                print(f"⚠️  Pexels API error: {resp.status_code}")
        else:
            print("⚠️  PEXELS_API_KEY not set")
        
        # Check metadata file
        from src.short_script_generator import SHORT_SCRIPT_FILE
        if SHORT_SCRIPT_FILE.exists():
            print("✓ Short script file available")
        else:
            print("⚠️  Run 'py main.py short-script' first")
        
        print("✅ Short video generation ready!")
        return True
        
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("   Run: pip install -r requirements.txt")
        return False
    except Exception as e:
        print(f"❌ Generation test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("SNS POSTING SETUP VERIFICATION")
    print("=" * 70)
    
    results = {
        "TikTok": test_tiktok_auth(),
        "Instagram": test_instagram_auth(),
        "Short Video Generation": test_short_video_generation(),
    }
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for service, passed in results.items():
        status = "✅" if passed else "⚠️"
        print(f"{status} {service}")
    
    if all(results.values()):
        print("\n✅ All tests passed! You can use:")
        print("   • py main.py short --tiktok")
        print("   • py main.py short --instagram")
        print("   • py main.py short --tiktok --instagram")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check SNS_API_SETUP_GUIDE.md for setup instructions.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
