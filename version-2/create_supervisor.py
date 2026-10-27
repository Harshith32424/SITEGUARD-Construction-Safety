"""
SITEGUARD V2 — Create Initial Supervisor Account
Run this script ONCE to set up the first supervisor login.

Usage:
    python create_supervisor.py

This script is for development/initial setup only.
Never hardcode passwords in source code.
"""
import os
import sys

# Ensure we run from the version-2 directory
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
sys.path.insert(0, script_dir)

import database_v2 as db

print("=" * 55)
print("  SITEGUARD V2 — Supervisor Account Setup")
print("=" * 55)
print()

username = input("Enter supervisor username: ").strip()
if not username:
    print("ERROR: Username cannot be empty.")
    sys.exit(1)

import getpass
password = getpass.getpass("Enter supervisor password (min 6 chars): ")
if len(password) < 6:
    print("ERROR: Password must be at least 6 characters.")
    sys.exit(1)

confirm = getpass.getpass("Confirm password: ")
if password != confirm:
    print("ERROR: Passwords do not match.")
    sys.exit(1)

full_name = input("Enter full name (optional): ").strip()
email = input("Enter email (optional): ").strip()

user_id = db.create_user(
    username=username,
    password=password,
    role='supervisor',
    full_name=full_name or username,
    email=email
)

if user_id:
    print()
    print(f"✓ Supervisor account created successfully!")
    print(f"  Username : {username}")
    print(f"  Role     : supervisor")
    print(f"  User ID  : {user_id}")
    print()
    print("You can now log in at: http://127.0.0.1:5001/login")
else:
    print(f"ERROR: Username '{username}' already exists. Choose a different username.")
    sys.exit(1)
