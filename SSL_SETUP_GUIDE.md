# SSL/HTTPS Setup with Certbot - Complete Guide

## Overview
This guide walks you through installing an SSL certificate from Let's Encrypt using Certbot on your GCE server. This provides FREE, automatically-renewed HTTPS for your domain.

---

## Prerequisites
- ✅ Nginx installed and running
- ✅ Domain pointing to your server IP (app.caudex.pro → 35.232.130.101)
- ✅ Port 443 (HTTPS) open in GCE firewall
- ✅ SSH access to your GCE server

---

## Step 1: Install Certbot

### In your GCE SSH Terminal, run:

```bash
sudo apt update
sudo apt install certbot python3-certbot-nginx -y
```

This installs:
- **certbot**: Tool for obtaining and managing Let's Encrypt certificates
- **python3-certbot-nginx**: Certbot plugin for automatic Nginx configuration

**Expected output:**
```
Reading package lists... Done
Setting up certbot...
Setting up python3-certbot-nginx...
Processing triggers...
```

---

## Step 2: Obtain SSL Certificate

### In your GCE SSH Terminal, run:

```bash
# REPLACE app.caudex.pro with your actual domain
sudo certbot --nginx -d app.caudex.pro
```

### What happens:
1. Certbot reads your Nginx configuration
2. Validates your domain ownership
3. Requests certificate from Let's Encrypt
4. Automatically modifies Nginx config to use HTTPS
5. Enables HTTP-to-HTTPS redirect

### Interactive prompts (respond as shown):

```
Saving debug log to /var/log/letsencrypt/letsencrypt.log
Plugins selected: Authenticator (nginx), Installer (nginx)

Enter email address (used for urgent renewal and security notices):
→ Enter your email (e.g., your@email.com)

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Please read the Terms of Service at
https://letsencrypt.org/documents/LE-SA-v1.3-September-21-2022.pdf. You must
agree in order to register with the Let's Encrypt CA and get a certificate.
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

(A)gree/(C)ancel:
→ Type: A

- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
Would you be willing, once your month is over, to share your email address
with the Electronic Frontier Foundation, a founding partner of the Let's Encrypt
project?
- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

(Y)es/(N)o:
→ Type: N (or Y if you want)
```

### Success response:

```
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/app.caudex.pro/fullchain.pem
Key is saved at: /etc/letsencrypt/live/app.caudex.pro/privkey.pem
This certificate expires on 2025-02-14.
Certbot has set up a scheduled task to automatically renew this certificate in the background.

Deploying certificate
Successfully deployed certificate for app.caudex.pro to /etc/nginx/sites-enabled/caudex.pro
Congratulations! You have successfully enabled HTTPS on https://app.caudex.pro
```

---

## Step 3: Verify SSL Configuration

### Check certificate details:

```bash
sudo certbot certificates
```

**Expected output:**
```
Found the following certs:
  Certificate Name: app.caudex.pro
    Serial Number: 1234567890abcdef
    Key Type: RSA
    Domains: app.caudex.pro
    Expiry Date: 2025-02-14
    Valid: True
    Issuers: R3
    Auto Renewal: enabled
```

### Check Nginx configuration:

```bash
sudo nginx -t
```

**Expected output:**
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration test is successful
```

### Reload Nginx:

```bash
sudo systemctl reload nginx
```

---

## Step 4: Verify HTTPS Works

### Test from your local machine:

```bash
# Test HTTPS connection
curl -I https://app.caudex.pro

# Or visit in browser:
# https://app.caudex.pro
```

**Expected response:**
```
HTTP/2 200
server: nginx
date: Fri, 14 Nov 2025 10:30:00 GMT
content-type: text/html
```

### Check SSL certificate in browser:
1. Navigate to `https://app.caudex.pro`
2. Click the padlock icon in address bar
3. View certificate details - should show "Let's Encrypt Authority X3"
4. Expiry date should be ~90 days from today

---

## Step 5: Automatic Renewal Setup

Certbot automatically sets up renewal via systemd timer. Verify it:

```bash
# Check renewal timer
sudo systemctl list-timers snap.certbot.renew.timer

# Or manually check renewal configuration
sudo cat /etc/letsencrypt/renewal/app.caudex.pro.conf
```

**Expected output shows:**
- Timer runs twice daily
- Auto-renewal enabled
- Certificate renews ~30 days before expiry

### Test renewal (dry-run):

```bash
sudo certbot renew --dry-run
```

Should complete successfully without errors.

---

## What Certbot Did to Nginx

Certbot automatically modified your Nginx config to:

1. **Added HTTPS block:**
   ```nginx
   listen 443 ssl http2;
   ssl_certificate /etc/letsencrypt/live/app.caudex.pro/fullchain.pem;
   ssl_certificate_key /etc/letsencrypt/live/app.caudex.pro/privkey.pem;
   ```

2. **Added HTTP redirect:**
   ```nginx
   # HTTP (port 80) redirects to HTTPS
   server {
       listen 80;
       server_name app.caudex.pro;
       return 301 https://$server_name$request_uri;
   }
   ```

3. **Added SSL security headers:**
   ```nginx
   ssl_protocols TLSv1.2 TLSv1.3;
   ssl_ciphers HIGH:!aNULL:!MD5;
   ```

---

## Common Issues & Fixes

### Issue: "Unable to locate package python3-certbot-nginx"
**Solution:** Update package list first
```bash
sudo apt update
sudo apt install certbot python3-certbot-nginx -y
```

### Issue: "Connection refused" when running certbot
**Solution:** Ensure Nginx is running
```bash
sudo systemctl start nginx
sudo systemctl status nginx
```

### Issue: "No matching domain found in Nginx config"
**Solution:** Verify Nginx config has server_name set
```bash
sudo grep "server_name" /etc/nginx/sites-enabled/caudex.pro
```

### Issue: "Challenge failed" or "Authorization error"
**Solution:** 
- Ensure domain DNS points to server IP
- Verify firewall allows port 80 and 443
- Wait a few minutes and try again

### Issue: "Certificate already exists"
**Solution:** Use --expand flag to add more domains
```bash
sudo certbot --nginx -d app.caudex.pro --expand
```

---

## Certificate Maintenance

### Manual renewal (if needed):
```bash
sudo certbot renew
```

### Check certificate expiry:
```bash
sudo ssl-cert-check -c /etc/letsencrypt/live/app.caudex.pro/fullchain.pem
```

### Force renewal:
```bash
sudo certbot renew --force-renewal
```

---

## SSL Security Best Practices

After setup, verify security:

```bash
# Test SSL configuration
openssl s_client -connect app.caudex.pro:443

# Check certificate chain
openssl s_client -connect app.caudex.pro:443 -showcerts

# Verify certificate is valid
openssl x509 -in /etc/letsencrypt/live/app.caudex.pro/fullchain.pem -text -noout
```

---

## Verification Checklist

- [ ] Certbot installed
- [ ] Certificate obtained (status: valid)
- [ ] Nginx reloaded
- [ ] HTTP redirects to HTTPS
- [ ] HTTPS works in browser (padlock shows)
- [ ] Certificate chain valid
- [ ] Auto-renewal enabled
- [ ] Firewall allows ports 80, 443

---

## Success!

Your domain now has:
- ✅ **HTTPS enabled** (encrypted connection)
- ✅ **Valid certificate** from Let's Encrypt
- ✅ **HTTP auto-redirect** to HTTPS
- ✅ **Automatic renewal** (90-day validity)
- ✅ **Modern SSL/TLS** (TLS 1.2+)

Your frontend and backend are now secure!

---

## Next Steps

1. **Configure backend** to accept HTTPS connections
2. **Update frontend** to use `https://app.caudex.pro`
3. **Monitor certificate** renewal (Certbot handles this automatically)
4. **Test end-to-end** deployment with real users

---

## Support Resources

- Let's Encrypt: https://letsencrypt.org
- Certbot Docs: https://certbot.eff.org
- Nginx SSL: https://nginx.org/en/docs/http/ngx_http_ssl_module.html
