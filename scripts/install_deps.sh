#!/bin/bash
# EVE Observer Dependency Installer for Hostinger
# Upload this script to your server and run: chmod +x install_deps.sh && ./install_deps.sh

echo "🚀 EVE Observer - Installing Python Dependencies"
echo "================================================"

# Check if we're in the right directory
if [ ! -f "eve-observer.php" ]; then
    echo "❌ Error: Please run this script from the eveObserver plugin directory"
    echo "   cd /home/u164580062/domains/eve.observer/public_html/wp-content/plugins/eveObserver"
    exit 1
fi

echo "📍 Current directory: $(pwd)"
echo "🐍 Python executable: /opt/alt/python311/bin/python3.11"

# Function to try pip installation
try_pip_install() {
    local pip_cmd="$1"
    local desc="$2"

    echo ""
    echo "🔍 Trying: $desc"
    echo "Command: $pip_cmd --version"

    if $pip_cmd --version >/dev/null 2>&1; then
        echo "✅ Pip available, installing packages..."

        # Install packages one by one for better error reporting
        packages=("python-dotenv" "requests" "requests-oauthlib" "aiohttp")

        for package in "${packages[@]}"; do
            echo "📦 Installing $package..."
            if $pip_cmd install --user "$package"; then
                echo "✅ $package installed successfully"
            else
                echo "❌ Failed to install $package"
                return 1
            fi
        done

        echo ""
        echo "🧪 Testing imports..."
        if /opt/alt/python311/bin/python3.11 -c "import dotenv, requests, aiohttp; print('✅ All imports successful!')"; then
            echo ""
            echo "🎉 SUCCESS! All dependencies installed."
            echo "   You can now test the sync button in WordPress admin."
            return 0
        else
            echo "❌ Import test failed"
            return 1
        fi
    else
        echo "❌ Pip not available with this command"
        return 1
    fi
}

# Try different pip approaches
pip_commands=(
    "/opt/alt/python311/bin/python3.11 -m pip:Python 3.11 module pip"
    "/opt/alt/python311/bin/pip3.11:Direct pip3.11 binary"
    "pip3.11:System pip3.11"
)

success=false
for cmd_desc in "${pip_commands[@]}"; do
    IFS=':' read -r pip_cmd desc <<< "$cmd_desc"
    if try_pip_install "$pip_cmd" "$desc"; then
        success=true
        break
    fi
done

if [ "$success" = false ]; then
    echo ""
    echo "❌ AUTOMATIC INSTALLATION FAILED"
    echo ""
    echo "📞 Please contact Hostinger support and ask them to install these Python packages:"
    echo "   - python-dotenv"
    echo "   - requests"
    echo "   - requests-oauthlib"
    echo "   - aiohttp"
    echo ""
    echo "   For the Python installation at: /opt/alt/python311/bin/python3.11"
    echo ""
    echo "🔗 Or provide them with this information:"
    echo "   - Hosting account: eve.observer"
    echo "   - Python version: 3.11.13"
    echo "   - Python path: /opt/alt/python311/bin/python3.11"
    echo "   - Required packages: python-dotenv, requests, requests-oauthlib, aiohttp"
fi

echo ""
echo "================================================"
echo "Installation attempt complete."