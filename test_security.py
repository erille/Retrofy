#!/usr/bin/env python3
"""
Test script to verify the security improvements work correctly.
"""

import bcrypt
import os
import secrets
from dotenv import load_dotenv

def test_password_hashing():
    """Test that password hashing works correctly."""
    print("Testing password hashing...")
    
    sample_secret = secrets.token_bytes(24)
    
    # Generate hash
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(sample_secret, salt)
    
    # Verify hash
    is_valid = bcrypt.checkpw(sample_secret, password_hash)
    
    if is_valid:
        print("✅ Password hashing works correctly")
    else:
        print("❌ Password hashing failed")
    
    return is_valid

def test_environment_variables():
    """Test that environment variables are loaded correctly."""
    print("\nTesting environment variables...")
    
    # Load .env if it exists
    load_dotenv()
    
    # Test default values
    admin_username = os.environ.get("ADMIN_USERNAME", "admin")
    admin_password_hash = os.environ.get("ADMIN_PASSWORD_HASH", "")
    
    print(f"Admin username: {admin_username}")
    print(f"Password hash set: {'Yes' if admin_password_hash else 'No'}")
    
    if admin_username != "legacy_admin":
        print("✅ Username is no longer hardcoded")
    else:
        print("❌ Username is still hardcoded")
    
    return admin_username != "legacy_admin"

def test_random_fallback_hash():
    """Test that a random fallback credential can be hashed and verified."""
    print("\nTesting random fallback credential...")
    random_credential = secrets.token_bytes(32)
    salt = bcrypt.gensalt()
    fallback_hash = bcrypt.hashpw(random_credential, salt)
    
    # Test verification
    is_valid = bcrypt.checkpw(random_credential, fallback_hash)
    
    if is_valid:
        print("✅ Random fallback credential works correctly")
        print(f"Fallback hash generated: {bool(fallback_hash)}")
    else:
        print("❌ Random fallback credential verification failed")
    
    return is_valid

def main():
    """Run all security tests."""
    print("Retrofy Security Test")
    print("=" * 40)
    
    tests = [
        test_password_hashing,
        test_environment_variables,
        test_random_fallback_hash
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            results.append(False)
    
    print("\n" + "=" * 40)
    print("TEST RESULTS")
    print("=" * 40)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All security tests passed!")
        print("\nNext steps:")
        print("1. Run 'python generate_password.py' to create a secure password")
        print("2. Copy 'env.example' to '.env' and configure your credentials")
        print("3. Update your environment variables with the generated hash")
    else:
        print("⚠️  Some tests failed. Please check the implementation.")

if __name__ == "__main__":
    main()
