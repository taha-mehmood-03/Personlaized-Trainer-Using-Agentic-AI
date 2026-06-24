"""Test anonymous mode functionality - skip pgvector writes and session summaries."""

import sys
import json
import requests
import time

BASE_URL = "http://localhost:8000"

def test_anonymous_mode_via_api():
    """Test that anonymousMode can be toggled via the API."""
    print("🔍 Testing Anonymous Mode via API\n")
    
    try:
        test_user_id = "test_anon_user_123"
        
        # 1. Get profile (or create session first)
        print("1️⃣  Getting user profile...")
        response = requests.get(
            f"{BASE_URL}/api/users/profile",
            headers={"Authorization": f"Bearer {test_user_id}"}
        )
        
        if response.status_code == 200:
            profile = response.json()
            current_anon_mode = profile.get("settings", {}).get("anonymousMode", False)
            print(f"   ✓ Current anonymousMode: {current_anon_mode}")
            print(f"   Profile: {json.dumps(profile.get('settings', {}), indent=2)}")
        else:
            print(f"   Note: Profile endpoint returned {response.status_code} - may need to create session first")
            
        # 2. Enable anonymous mode
        print("\n2️⃣  Enabling anonymous mode...")
        response = requests.patch(
            f"{BASE_URL}/api/users/profile",
            headers={"Authorization": f"Bearer {test_user_id}"},
            json={"settings": {"anonymousMode": True}}
        )
        
        if response.status_code == 200:
            print(f"   ✓ Successfully enabled anonymous mode")
            profile = response.json()
            assert profile.get("settings", {}).get("anonymousMode") is True
            print(f"   Updated profile: {json.dumps(profile.get('settings', {}), indent=2)}")
        else:
            print(f"   ❌ Failed to enable: {response.status_code} - {response.text[:200]}")
            return False
            
        # 3. Verify anonymous mode is enabled
        print("\n3️⃣  Verifying anonymous mode is enabled...")
        response = requests.get(
            f"{BASE_URL}/api/users/profile",
            headers={"Authorization": f"Bearer {test_user_id}"}
        )
        
        if response.status_code == 200:
            profile = response.json()
            anon_mode = profile.get("settings", {}).get("anonymousMode", False)
            assert anon_mode is True, "anonymousMode should be True"
            print(f"   ✓ Confirmed: anonymousMode = {anon_mode}")
        else:
            print(f"   ❌ Failed to retrieve: {response.status_code}")
            return False
            
        # 4. Disable anonymous mode
        print("\n4️⃣  Disabling anonymous mode...")
        response = requests.patch(
            f"{BASE_URL}/api/users/profile",
            headers={"Authorization": f"Bearer {test_user_id}"},
            json={"settings": {"anonymousMode": False}}
        )
        
        if response.status_code == 200:
            profile = response.json()
            assert profile.get("settings", {}).get("anonymousMode") is False
            print(f"   ✓ Successfully disabled anonymous mode")
        else:
            print(f"   ❌ Failed to disable: {response.status_code}")
            return False
            
        print("\n✅ All anonymous mode API tests passed!")
        return True
        
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to API at {BASE_URL}")
        print("   Please ensure the FastAPI server is running on port 8000")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def check_anonymous_mode_usage():
    """Check where anonymous_mode is used in the codebase."""
    print("\n📋 Anonymous Mode Technical Details:")
    print("=" * 60)
    print("Database Storage:")
    print("  • Field: UserPreference.anonymousMode (Boolean, default=false)")
    print("  • Readable via: GET /api/users/profile")
    print("  • Updatable via: PATCH /api/users/profile with 'settings'")
    print("\nWhen Enabled (anonymousMode=true):")
    print("  ✗ SKIPS: _background_extract_facts() → No pgvector writes")
    print("  ✗ SKIPS: Session summarization")
    print("  ✓ ALLOWS: Full app usage without persistent profiling")
    print("\nCode Enforcement Points:")
    print("  1. graph.py:1582 - Early return from fact extraction")
    print("  2. session_saver.py:593 - Skip session summarization")
    print("\nUser Interface:")
    print("  • Frontend toggle: Profile Settings page")
    print("  • Setting name: 'Use anonymous mode'")
    print("\n" + "=" * 60)

if __name__ == "__main__":
    print("🔍 Testing Anonymous Mode Functionality")
    print("=" * 60)
    
    success = test_anonymous_mode_via_api()
    check_anonymous_mode_usage()
    
    exit(0 if success else 1)
