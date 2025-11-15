## Frontend Deployment Guide

The React app has been successfully built locally. Follow these steps to deploy to production:

### Option 1: Deploy via GCP Web Console (Recommended)

1. Go to GCP Console: https://console.cloud.google.com/compute/instances
2. Find "caudex-pro-backend-vm" and click SSH to open web terminal
3. Run these commands:

```bash
cd ~/George
git pull origin master
cd frontend
rm -rf dist node_modules package-lock.json
npm install --legacy-peer-deps
npm run build
```

4. After build completes, copy files to web root:

```bash
sudo rm -rf /var/www/caudex-pro/*
sudo cp -r dist/* /var/www/caudex-pro/
sudo chown -R sw33fami1y:sw33fami1y /var/www/caudex-pro/
```

5. Verify deployment:

```bash
curl https://app.caudex.pro/
# Should return HTML with <div id="root"></div>
```

### Option 2: Deploy via SCP (If SSH keys are configured)

```bash
cd c:\Users\kael_\George\frontend
scp -r dist/* sw33fami1y@35.232.130.101:/var/www/caudex-pro/
```

### Files Built

The build process created:
- `dist/index.html` - React app entry point (0.42 kB) ✅
- `dist/assets/index-BY1UT5kJ.js` - React app bundle (202.48 kB)
- `dist/assets/index-BY1UT5kJ.css` - App styling (0.37 kB)

### Verification Checklist

After deployment:
- [ ] Visit https://app.caudex.pro in browser
- [ ] Should see React login page (not old HTML)
- [ ] Browser console should have no errors
- [ ] Try logging in
- [ ] Test file upload feature

### Built Configuration

- ✅ React 18.3.1
- ✅ React Router v6 for navigation
- ✅ TypeScript support
- ✅ Vite build tool
- ✅ Proper entry point (src/main.tsx)
- ✅ LoginView component connected
- ✅ AppContext for state management

### Build Output

```
vite v7.2.2 building client environment for production...
✓ 84 modules transformed.
dist/index.html                   0.42 kB │ gzip:  0.29 kB
dist/assets/index-D_8AGqEa.css    0.37 kB │ gzip:  0.28 kB
dist/assets/index-BY1UT5kJ.js   202.48 kB │ gzip: 68.85 kB
✓ built in 1.42s
```

### Troubleshooting

If you still see old HTML:
1. Check git was pulled: `cd ~/George && git log --oneline | head -2`
2. Verify new index.html: `head -5 ~/George/frontend/dist/index.html`
3. Check web root: `cat /var/www/caudex-pro/index.html | head -5`
4. Hard refresh browser: Ctrl+Shift+R (or Cmd+Shift+R on Mac)
5. Clear browser cache
