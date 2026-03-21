#!/bin/bash

# Setup Script for Multi-Course Attendance Management Portal
# This script creates a virtual environment, installs dependencies, and initializes the database

set -e  # Exit on error

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Multi-Course Attendance Management Portal - Setup Script     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Navigate to script directory
cd "$(dirname "$0")"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed."
    echo "   Please install Python 3 and try again."
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"
echo ""

# Create virtual environment
echo "📦 Creating virtual environment..."
if [ -d "venv" ]; then
    echo "⚠️  Virtual environment already exists. Skipping creation."
else
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi
echo ""

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Install dependencies for Module-B
echo "📥 Installing dependencies for Module-B..."
cd Module-B
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Initialize database
echo "🗄️  Initializing database..."
python3 init_db.py
echo "✓ Database initialized"
echo ""

# Success message
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                    ✅ Setup Complete!                          ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "To start the application:"
echo ""
echo "  1. Activate the virtual environment (if not already active):"
echo "     source venv/bin/activate"
echo ""
echo "  2. Navigate to Module-B:"
echo "     cd Module-B"
echo ""
echo "  3. Run the application:"
echo "     python run.py"
echo ""
echo "  4. Open your browser and visit:"
echo "     http://localhost:5050"
echo ""
echo "Default credentials:"
echo "  Username: admin"
echo "  Password: password123"
echo ""
echo "════════════════════════════════════════════════════════════════"
