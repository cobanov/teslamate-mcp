#!/usr/bin/env python3
"""Generate secure bearer tokens for TeslaMate MCP authentication"""

import secrets
import string
import sys

def generate_token(length=32):
    """Generate a secure random token"""
    # Use a mix of letters, digits, and some safe special characters
    alphabet = string.ascii_letters + string.digits + "-_"
    token = ''.join(secrets.choice(alphabet) for _ in range(length))
    return token

def main():
    print("TeslaMate MCP Bearer Token Generator")
    print("=" * 40)
    
    # Ask for token length
    try:
        length = input("Token length (default 32, recommended min 32): ").strip()
        length = int(length) if length else 32
        
        if length < 16:
            print("Warning: Token length should be at least 16 characters for security")
            confirm = input("Continue anyway? (y/N): ").strip().lower()
            if confirm != 'y':
                sys.exit(0)
    except ValueError:
        print("Invalid input, using default length of 32")
        length = 32
    
    # Generate token
    token = generate_token(length)
    
    print("\nGenerated Bearer Token:")
    print("-" * 40)
    print(token)
    print("-" * 40)
    
    print("\nAdd this to your .env file:")
    print(f"AUTH_TOKEN={token}")
    
    print("\nUse in MCP client config:")
    print(f'"Authorization": "Bearer {token}"')

if __name__ == "__main__":
    main() 