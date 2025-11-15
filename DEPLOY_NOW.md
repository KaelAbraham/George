# EXECUTE THIS ON GCP PRODUCTION SERVER

## Step 1: Open GCP Console SSH

Go to: https://console.cloud.google.com/compute/instances
Find: "caudex-pro-backend-vm"
Click: SSH button to open web terminal

## Step 2: Copy & Paste ALL of this into the web terminal:

```bash
cd ~/George && \
git pull origin master && \
cd frontend && \
rm -rf dist node_modules package-lock.json && \
npm install --legacy-peer-deps && \
npm run build && \
sudo rm -rf /var/www/caudex-pro/* && \
sudo cp -r dist/* /var/www/caudex-pro/ && \
sudo chown -R sw33fami1y:sw33fami1y /var/www/caudex-pro/ && \
echo "✅ Deployment complete!" && \
echo "🌐 Visit: https://app.caudex.pro/" && \
curl https://app.caudex.pro/ 2>/dev/null | head -20
```

## Step 3: Verify Deployment

After the commands complete, you should see:
- ✅ "npm run build" output showing "✓ built in X ms"
- ✅ HTML output starting with `<!DOCTYPE html>`
- ✅ Contains: `<div id="root"></div>`

## Step 4: Test in Browser

1. Open: https://app.caudex.pro/
2. Hard refresh: **Ctrl+Shift+R** (or Cmd+Shift+R on Mac)
3. Should see: **React Login Page**
4. Should NOT see: Old HTML with upload form

## Troubleshooting

**Q: Still seeing old HTML?**
A: Clear browser cache and hard refresh:
   - Ctrl+Shift+R (Windows/Linux)
   - Cmd+Shift+R (Mac)

**Q: Want to check server files?**
A: Run on server:
   ```bash
   head -20 /var/www/caudex-pro/index.html
   # Should show: <!DOCTYPE html> ... <div id="root"></div>
   
   ls -lh /var/www/caudex-pro/
   # Should show: index.html and assets/ folder
   ```

**Q: Check build was correct?**
A: Run on server:
   ```bash
   cd ~/George/frontend && npm run build
   # Should see: "✓ built in X ms"
   ```

## What Was Fixed Locally

✅ Replaced old test code with React app entry point (main.tsx)
✅ Added React, React DOM, React Router dependencies
✅ Added React plugin to Vite configuration
✅ Replaced old HTML file with proper React template
✅ Added TypeScript configuration
✅ Built React app successfully (84 modules)
✅ Verified dist folder contains correct files
✅ Pushed all changes to git master branch

## Files Ready for Deployment

- ✅ frontend/dist/index.html (415 bytes) - React app
- ✅ frontend/dist/assets/index-BY1UT5kJ.js (202.5 KB) - React bundle
- ✅ frontend/dist/assets/index-D_8AGqEa.css (366 bytes) - Styles
- ✅ Git commits pushed: cb762aa, a27e548

## One-Line Quick Deploy

If you want to do it in one command:

```bash
cd ~/George && git pull && cd frontend && rm -rf dist node_modules && npm install --legacy-peer-deps && npm run build && sudo rm -rf /var/www/caudex-pro/* && sudo cp -r dist/* /var/www/caudex-pro/ && sudo chown -R sw33fami1y:sw33fami1y /var/www/caudex-pro/ && echo "✅ Done!" && curl https://app.caudex.pro/ 2>/dev/null | head -5
```

---

**Ready?** Copy the command from Step 2 and paste it into the GCP console!
