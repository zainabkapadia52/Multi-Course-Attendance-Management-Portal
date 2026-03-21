#!/bin/bash

# Quick start script for the application
# Run this after completing setup.sh

set -e

cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "   Please run ./setup.sh first"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Navigate to Module-B and run the app
cd Module-B

echo "🚀 Starting Multi-Course Attendance Management Portal..."
echo "   Server will run on http://localhost:5050"
echo ""
echo "   Press Ctrl+C to stop the server"
echo ""

python run.py
