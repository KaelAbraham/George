# DEPLOYMENT CHECKLIST

## Pre-Deployment ✅

- [x] Root cause identified: Old HTML in index.html
- [x] React entry point created: src/main.tsx  
- [x] Vite config updated with React plugin
- [x] index.html cleaned (453 lines → 8 lines)
- [x] package.json updated with React dependencies
- [x] TypeScript configured (tsconfig.json created)
- [x] CSS entry point created (index.css)
- [x] npm install successful (60 packages)
- [x] npm run build successful
- [x] React app verified in dist/index.html
- [x] Git commits created and pushed
- [x] dist/ folder ready for deployment

## Deployment Steps (On GCP Server)

Follow these in order:

- [ ] Open GCP Console SSH
- [ ] Navigate to ~/George
- [ ] Git pull latest code
- [ ] Navigate to frontend directory
- [ ] Clean old build artifacts
- [ ] Run npm install --legacy-peer-deps
- [ ] Run npm run build
- [ ] Verify build output shows "✓ built"
- [ ] Clear /var/www/caudex-pro/
- [ ] Copy dist files to /var/www/caudex-pro/
- [ ] Set correct permissions
- [ ] Verify index.html in web root

## Post-Deployment Verification ✅

- [ ] Visit https://app.caudex.pro/ 
- [ ] Page loads without errors
- [ ] Browser console has no 404 errors
- [ ] React login page visible
- [ ] Old HTML NOT visible
- [ ] Hard refresh (Ctrl+Shift+R) shows React app
- [ ] Login button present
- [ ] No console errors in browser dev tools
- [ ] Assets load correctly (CSS, JS)

## Troubleshooting Commands

If something goes wrong, run these on the server:

```bash
# Check Git pulled correctly
git log --oneline | head -2

# Check React app was built
ls -lh ~/George/frontend/dist/

# Check files were deployed to web root
ls -lh /var/www/caudex-pro/

# Check index.html content
head -10 /var/www/caudex-pro/index.html
# Should show: <!DOCTYPE html> ... <div id="root"></div>

# Check for old HTML (should return 0)
grep -c "George - Knowledge Extractor" /var/www/caudex-pro/index.html

# Check Nginx is serving the file
curl https://app.caudex.pro/ | head -20

# Check permissions
ls -la /var/www/caudex-pro/ | head -5
```

## Browser Testing

After deployment, test in browser:

1. **Test 1: Fresh Load**
   - [ ] Open https://app.caudex.pro/
   - [ ] Hard refresh: Ctrl+Shift+R
   - [ ] Should see React login page

2. **Test 2: Console Check**
   - [ ] Open Developer Tools: F12
   - [ ] Go to Console tab
   - [ ] Should see no 404 errors
   - [ ] Should see no React warnings

3. **Test 3: Network Check**
   - [ ] Open Developer Tools: F12
   - [ ] Go to Network tab
   - [ ] Reload page
   - [ ] Check:
     - [ ] index.html loads (not 404)
     - [ ] index-*.js loads (not 404)
     - [ ] index-*.css loads (not 404)

4. **Test 4: Old HTML Check**
   - [ ] In page HTML, search for "root"
   - [ ] Should find: `<div id="root"></div>`
   - [ ] Should NOT find: "George - Knowledge Extractor"
   - [ ] Should NOT find: upload-area div

## Success Indicators

✅ React login page loads
✅ No 404 errors in console
✅ No old HTML visible
✅ Assets (CSS, JS) load successfully
✅ Page is responsive
✅ Login form is functional

## If Still Seeing Old HTML

1. Clear browser cache completely
2. Try incognito/private window
3. Check server-side:
   ```bash
   sudo rm -rf /var/www/caudex-pro/*
   sudo cp -r ~/George/frontend/dist/* /var/www/caudex-pro/
   sudo systemctl restart nginx
   ```
4. Wait 30 seconds and refresh browser
5. Verify with: `curl https://app.caudex.pro/ 2>/dev/null | grep root`

## Final Status

Once all checks pass:

- [x] Frontend build: Complete ✅
- [x] Git changes: Pushed ✅
- [ ] Server deployment: Pending (Execute DEPLOY_NOW.md)
- [ ] Browser verification: Pending
- [ ] Production ready: Pending verification

---

**Next Action:** Follow instructions in DEPLOY_NOW.md to deploy to production server
