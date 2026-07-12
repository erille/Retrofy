#!/usr/bin/env python3
"""
Utility script to generate secure password hashes for Retrofy admin user.
Run this script to generate a password hash that can be used in environment variables.
"""

import bcrypt
import getpass

def generate_password_hash():
    """Generate a bcrypt hash for a password."""
    print("Retrofy Password Hash Generator")
    print("=" * 40)
    
    # Get password securely
    password = getpass.getpass("Enter the admin password: ")
    password_confirm = getpass.getpass("Confirm the admin password: ")
    
    if password != password_confirm:
        print("Error: Passwords do not match!")
        return
    
    if len(password) < 8:
        print("Warning: Password is less than 8 characters. Consider using a stronger password.")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            return
    
    # Generate hash
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
    
    print("\n" + "=" * 40)
    print("PASSWORD HASH GENERATED")
    print("=" * 40)
    print("Username: admin")
    print(f"Password Hash: {password_hash.decode('utf-8')}")
    print("\nAdd these to your .env file:")
    print("ADMIN_USERNAME=admin")
    print(f"ADMIN_PASSWORD_HASH={password_hash.decode('utf-8')}")
    print("\nOr set as environment variables:")
    print("export ADMIN_USERNAME=admin")
    print(f"export ADMIN_PASSWORD_HASH={password_hash.decode('utf-8')}")

if __name__ == "__main__":
    generate_password_hash()
