#!/bin/bash
# Commands to run in GCP Web SSH Console

# 1. Clear the web directory
sudo rm -rf /var/www/caudex-pro/*

# 2. Create a temporary directory for upload
mkdir -p /tmp/frontend-upload
cd /tmp/frontend-upload

# 3. Check permissions
ls -la /var/www/caudex-pro

# 4. Display ready for upload
echo "Ready to receive frontend files"
echo "Directory: /var/www/caudex-pro"
