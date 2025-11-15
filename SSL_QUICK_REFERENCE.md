# SSL Setup - Quick Reference

## Quick Command Summary

### Install Certbot
```bash
ssh sw33fami1y@35.232.130.101
sudo apt update
sudo apt install certbot python3-certbot-nginx -y
```

### Get SSL Certificate
```bash
sudo certbot --nginx -d app.caudex.pro
```
- Email: your@email.com
- Agree to terms: A
- Share email (optional): N

### Verify Setup
```bash
# Check certificate
sudo certbot certificates

# Test Nginx config
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

### Test HTTPS
```bash
# From local machine:
curl -I https://app.caudex.pro

# Or visit in browser:
# https://app.caudex.pro
```

### Check Auto-Renewal
```bash
sudo systemctl list-timers snap.certbot.renew.timer
sudo certbot renew --dry-run
```

---

## File Locations

- **Certificate**: `/etc/letsencrypt/live/app.caudex.pro/fullchain.pem`
- **Private Key**: `/etc/letsencrypt/live/app.caudex.pro/privkey.pem`
- **Nginx Config**: `/etc/nginx/sites-enabled/caudex.pro`
- **Certbot Config**: `/etc/letsencrypt/renewal/app.caudex.pro.conf`
- **Renewal Timer**: Automatic via systemd (runs twice daily)

---

## Certificate Details

- **Provider**: Let's Encrypt (Free)
- **Validity**: 90 days
- **Auto-Renewal**: Yes (runs ~30 days before expiry)
- **Supported**: TLS 1.2, TLS 1.3
- **Grade**: A+ (with modern ciphers)

---

## Done! ✅

Your setup is complete when you see:
```
Congratulations! You have successfully enabled HTTPS on https://app.caudex.pro
```

Then test with your browser or curl.
