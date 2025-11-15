#!/bin/bash
# Frontend Deployment Script for George
# Run this on the production server to deploy the React app

set -e  # Exit on error

echo "================================"
echo "George Frontend Deployment"
echo "================================"
echo ""

# Navigate to project
cd ~/George
echo "📁 Project directory: $(pwd)"
echo ""

# Pull latest changes
echo "📥 Pulling latest code from git..."
git pull origin master
echo "✅ Git pull complete"
echo ""

# Navigate to frontend
cd frontend
echo "📁 Frontend directory: $(pwd)"
echo ""

# Clean old builds
echo "🧹 Cleaning old node_modules and build artifacts..."
rm -rf node_modules package-lock.json dist
echo "✅ Cleaned"
echo ""

# Install dependencies
echo "📦 Installing npm dependencies..."
npm install
echo "✅ Dependencies installed"
echo ""

# Build the React app
echo "🔨 Building React app with Vite..."
npm run build
echo "✅ Build complete"
echo ""

# Copy to web root
echo "📤 Copying built files to web server..."
sudo rm -rf /var/www/caudex-pro/*
sudo cp -r dist/* /var/www/caudex-pro/
sudo chown -R sw33fami1y:sw33fami1y /var/www/caudex-pro/
echo "✅ Files copied to /var/www/caudex-pro/"
echo ""

# Verify
echo "🔍 Verifying deployment..."
ls -la /var/www/caudex-pro/ | head -10
echo ""

# Check if index.html exists and has React content
if grep -q "root" /var/www/caudex-pro/index.html; then
    echo "✅ React app deployed successfully!"
    echo "🌐 Visit: https://app.caudex.pro/"
else
    echo "❌ Warning: index.html may not be the React app"
fi

echo ""
echo "✅ Deployment complete!"
