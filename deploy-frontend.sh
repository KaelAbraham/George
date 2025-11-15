#!/bin/bash
cd ~/George
git pull origin master
cd frontend
rm -rf node_modules package-lock.json dist
npm install
npm run build
