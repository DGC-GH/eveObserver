#!/opt/alt/python311/bin/python3.11
"""
EVE Observer Dependency Installer
Run this script on your Hostinger server to install required Python packages
"""

import subprocess
import sys
import os

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"\n🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {description} - SUCCESS")
            if result.stdout.strip():
                print(f"Output: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ {description} - FAILED")
            print(f"Error: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"❌ {description} - ERROR: {str(e)}")
        return False

def main():
    print("🚀 EVE Observer Dependency Installer")
    print("=" * 40)

    # Check Python version
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")

    # Required packages
    packages = [
        'python-dotenv',
        'requests',
        'requests-oauthlib',
        'aiohttp'
    ]

    print(f"\n📦 Installing {len(packages)} required packages...")

    # Try different pip approaches
    pip_commands = [
        '/opt/alt/python311/bin/python3.11 -m pip install --user',
        'pip3.11 install --user',
        '/opt/alt/python311/bin/pip3.11 install --user'
    ]

    success = False
    for pip_cmd in pip_commands:
        print(f"\n🔍 Trying pip command: {pip_cmd}")
        if run_command(f'{pip_cmd} --version', 'Check pip availability'):
            # Install packages
            for package in packages:
                if run_command(f'{pip_cmd} {package}', f'Install {package}'):
                    success = True
                else:
                    success = False
                    break
            if success:
                break

    if success:
        print("\n🎉 All packages installed successfully!")
        print("\n🧪 Testing imports...")

        # Test imports
        test_imports = [
            ('dotenv', 'from dotenv import load_dotenv'),
            ('requests', 'import requests'),
            ('requests_oauthlib', 'import requests_oauthlib'),
            ('aiohttp', 'import aiohttp')
        ]

        all_passed = True
        for module_name, import_stmt in test_imports:
            try:
                exec(import_stmt)
                print(f"✅ {module_name} - OK")
            except ImportError as e:
                print(f"❌ {module_name} - FAILED: {e}")
                all_passed = False

        if all_passed:
            print("\n🎯 All tests passed! Your EVE Observer should now work.")
        else:
            print("\n⚠️  Some imports failed. You may need to contact Hostinger support.")

    else:
        print("\n❌ Failed to install packages automatically.")
        print("Please contact Hostinger support or try manual installation:")
        print("1. SSH into your server")
        print("2. Run: /opt/alt/python311/bin/python3.11 -m pip install --user python-dotenv requests requests-oauthlib aiohttp")

if __name__ == '__main__':
    main()