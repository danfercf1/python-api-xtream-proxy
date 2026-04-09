# Security Guide for Xtream Proxy Gateway

## Overview

This document explains the security model of this Xtream Codes proxy gateway and the available protections.

---

## ⚠️ Critical Security Reality: URL-Based Credentials

**Xtream Codes API requires credentials in URL query parameters.** This is a fundamental design limitation of the protocol that cannot be changed without breaking compatibility with IPTV players.

### Where Credentials Are Visible

| Location | With Proxy Mode OFF | With Proxy Mode ON |
|----------|---------------------|--------------------|
| Your gateway logs | ✅ Yes | ✅ Yes |
| Upstream server logs | ✅ Yes | ✅ Yes |
| Client browser/player logs | ✅ Yes | ❌ **No** |
| Client browser history | ✅ Yes | ❌ **No** |
| Network traffic (HTTP) | ✅ Yes | ✅ Yes |
| Network traffic (HTTPS) | ✅ Encrypted | ✅ Encrypted |

### What This Means

1. **Anyone with access to gateway or upstream logs can see credentials**
2. **With Proxy Mode OFF**: Client can see and potentially log/store the upstream URL with credentials
3. **Network sniffing**: If not using HTTPS, credentials are visible in transit

---

## 🔐 Security Features & Mitigations

### 1. Proxy Mode (PROXY_MODE_ENABLED)

**Purpose**: Hide upstream URL and credentials from clients

**How it works**:
- **OFF (default)**: Gateway sends 302 redirect to upstream. Client connects directly.
- **ON**: Gateway fetches from upstream and returns content. Client never sees upstream URL.

**Trade-offs**:

| Aspect | Redirect (OFF) | Proxy (ON) |
|--------|----------------|------------|
| Client sees upstream URL | Yes | No |
| Gateway bandwidth usage | Low (just redirects) | High (streams pass through) |
| Latency | Lower | Higher (extra hop) |
| Server load | Lower | Higher |
| Compatibility | 100% | May have issues with some players |

**Recommendation**:
- Enable for API endpoints (`player_api.php`, `get.php`, `xmltv.php`)
- Disable for stream segments (`.ts`, `.m3u8` files) to avoid bandwidth overload

### 2. Password Encryption at Rest

**Purpose**: Protect stored passwords in database

**Implementation**: AES-128 encryption via Fernet

**Configuration**:
```bash
ENABLE_PASSWORD_ENCRYPTION=true
ENCRYPTION_KEY=your_generated_key_here
```

**Note**: This only protects passwords in YOUR database. The upstream provider still receives credentials in plaintext (Xtream protocol requirement).

### 3. SSL/TLS Configuration

**Purpose**: Encrypt traffic between components

**Current state**:
- Gateway → Client: Use HTTPS reverse proxy (nginx/traefik recommended)
- Gateway → Upstream: Configurable via `SSL_VERIFY_UPSTREAM`

**Configuration**:
```bash
# Set to true only if upstream has valid SSL certificates
SSL_VERIFY_UPSTREAM=false
```

**Important**: Most Xtream providers use self-signed certificates, so verification is disabled by default.

### 4. Security Headers

**Purpose**: Protect against common web attacks

**Headers added**:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy: default-src 'self'`

### 5. Audit Logging

**Purpose**: Track authentication attempts

**Logged events**:
- Failed authentication attempts
- Successful authentications
- Suspicious redirect attempts

**Enable**:
```bash
AUDIT_LOG_ENABLED=true
```

### 6. Input Validation

**Purpose**: Prevent injection attacks

**Validations**:
- Path traversal blocked (`..`, absolute paths)
- URL injection blocked (special characters)
- SSRF protection (private IPs blocked)
- Action parameter whitelisting (alphanumeric only)

### 7. Rate Limiting

**Purpose**: Prevent brute force attacks

**Configuration**:
```bash
RATE_LIMIT_PLAYER_API_PER_MINUTE=30
RATE_LIMIT_REDIRECT_PER_MINUTE=120
```

---

## 🛡️ Best Practices

### 1. Use HTTPS Everywhere

Put the gateway behind an HTTPS reverse proxy:

```nginx
# Example nginx configuration
server {
    listen 443 ssl;
    server_name your-gateway.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 2. Enable Proxy Mode for API Only

Edit `proxy_utils.py` to selectively enable proxy mode:

```python
def should_use_proxy_mode(request_path: str) -> bool:
    # Only proxy API endpoints, not streams
    proxy_paths = [
        '/player_api.php',
        '/get.php',
        '/xmltv.php',
    ]
    # Don't proxy streams (would use too much bandwidth)
    stream_extensions = ['.ts', '.m3u8', '.mp4']
    
    for ext in stream_extensions:
        if request_path.endswith(ext):
            return False
    
    for proxy_path in proxy_paths:
        if request_path.startswith(proxy_path):
            return True
    
    return False
```

### 3. Secure Database

- Use strong, random passwords
- Limit database network access
- Enable encryption at rest (if supported)
- Regular backups

### 4. Monitor Logs

Watch for suspicious activity:

```bash
# Failed auth attempts
docker logs <container> | grep "auth_failed"

# Blocked redirect attempts
docker logs <container> | grep "Blocked suspicious redirect"

# Rate limiting
docker logs <container> | grep "rate_limited"
```

### 5. Credential Rotation

Since credentials are in URLs:
- Use unique credentials per user
- Rotate credentials periodically
- Monitor for unauthorized usage

---

## 🔍 Security Checklist

Before deploying to production:

- [ ] Changed default passwords (MySQL, gateway)
- [ ] Generated and set ENCRYPTION_KEY
- [ ] Enabled password encryption
- [ ] Enabled audit logging
- [ ] Configured rate limiting
- [ ] Placed behind HTTPS reverse proxy
- [ ] Set up log monitoring
- [ ] Configured proxy mode as needed
- [ ] Restricted database network access
- [ ] Backed up encryption key (lose key = lose passwords)

---

## ⚡ Quick Start (Secure)

```bash
# 1. Generate encryption key
./scripts/generate_encryption_key.sh

# 2. Copy to .env
cp .env.example .env
# Edit .env and set:
# - ENCRYPTION_KEY (from step 1)
# - Strong MYSQL_ROOT_PASSWORD and MYSQL_PASSWORD
# - PROXY_MODE_ENABLED=true (optional, see trade-offs)

# 3. Deploy with HTTPS reverse proxy (nginx/traefik)

# 4. Start
docker compose up -d

# 5. Monitor logs
docker logs -f python-api-xtream-proxy-api-1
```

---

## 🆘 Incident Response

If credentials are compromised:

1. **Immediately** rotate credentials on upstream provider
2. Update credentials in gateway `.env`
3. Restart gateway: `docker compose restart`
4. Review logs for unauthorized access patterns
5. Notify affected users if applicable

---

## 📞 Security Issues

For security-related questions or to report vulnerabilities:

1. Check logs for suspicious activity
2. Review audit trail
3. Consider enabling proxy mode for additional protection
4. Ensure HTTPS is used for all connections

---

**Remember**: Security is about risk management, not elimination. This gateway provides significant improvements over direct upstream access while maintaining Xtream Codes compatibility.
