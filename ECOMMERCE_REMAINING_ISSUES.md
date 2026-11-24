# DesiDhar E-Commerce Remaining Issues

## Issues Requiring External Dependencies

### 1. Razorpay Production Credentials (BLOCKER)
**Status:** BLOCKED  
**Impact:** Cannot process real payments or test refunds in sandbox  
**Required:** 
- Razorpay live account with KYC completed
- Live key_id and key_secret
- Webhook secret configured in Razorpay dashboard
- Webhook URL: `https://api.desidhar.com/payments/webhook`

**Workaround:** Development uses mock provider (`PAYMENT_PROVIDER=mock`)

### 2. SMTP Email Configuration (BLOCKER)
**Status:** BLOCKED  
**Impact:** OTP emails not sent in production  
**Required:**
- Production SMTP credentials (Gmail/SendGrid/AWS SES)
- Verified sender domain
- SPF/DKIM/DMARC configured

**Workaround:** Development logs OTP to console

### 3. Production Infrastructure (BLOCKER)
**Status:** BLOCKED  
**Impact:** Cannot deploy to production  
**Required:**
- PostgreSQL production database
- Redis for rate limiting (optional, in-memory works)
- Load balancer with SSL termination
- Domain with valid TLS certificate
- Container orchestration (K8s/ECS) or VM deployment

## Issues Requiring Business Decisions

### 4. Refresh Token Implementation (HIGH)
**Status:** OPEN  
**Current:** Access tokens only (7-day customer, 30-min admin)  
**Risk:** Long-lived tokens in localStorage vulnerable to XSS  
**Recommended:** 
- Implement refresh token rotation
- Store refresh tokens in HttpOnly Secure cookies
- Shorten access token to 15-30 minutes
- Add token revocation on logout/password change

### 5. CSRF Protection (MEDIUM)
**Status:** OPEN  
**Current:** JWT in Authorization header (Bearer)  
**Risk:** Low for Bearer tokens, but state-changing operations should have CSRF protection if cookies used  
**Recommended:** Add CSRF tokens for any cookie-based auth

### 6. Email Verification Flow (MEDIUM)
**Status:** OPEN  
**Current:** OTP verifies email implicitly  
**Gap:** No explicit email verification required before account use  
**Recommended:** Add `email_verified` flag to User model, require for sensitive operations

### 7. Password Reset Flow (MEDIUM)
**Status:** PARTIAL  
**Current:** Schema supports but no API endpoints  
**Required:** 
- `POST /auth/password/forgot` - send reset OTP
- `POST /auth/password/reset` - verify OTP + new password
- Rate limiting on both endpoints

### 8. Guest Cart Merge (LOW)
**Status:** OPEN  
**Current:** Frontend has localStorage cart, backend has user cart  
**Gap:** No merge logic on login  
**Recommended:** Implement `merge_guest_cart` on customer login

## Technical Debt / Improvements

### 9. Database Connection Pooling (MEDIUM)
**Status:** OPEN  
**Current:** Default SQLAlchemy pool settings  
**Recommended:** Tune pool_size, max_overflow for production load

### 10. Caching Strategy (MEDIUM)
**Status:** OPEN  
**Current:** No caching layer  
**Recommended:** 
- Redis for product catalog caching
- Cache invalidation on product updates
- Rate limit counters in Redis (not in-memory)

### 11. Background Job Processing (MEDIUM)
**Status:** OPEN  
**Current:** Email sent via BackgroundTasks (in-process)  
**Recommended:** 
- Celery + Redis for reliable job queue
- Retry logic for email/webhook delivery
- Dead letter queue for failed jobs

### 12. Webhook Retry Handling (MEDIUM)
**Status:** OPEN  
**Current:** Single webhook processing attempt  
**Recommended:** 
- Exponential backoff retry
- Idempotency key storage for 24h
- Alert on repeated failures

### 13. Audit Logging (LOW)
**Status:** OPEN  
**Current:** OrderStatusHistory tracks status changes  
**Recommended:** 
- Admin action audit log (who did what when)
- Payment/refund audit trail
- Login/logout events

### 14. Search Optimization (LOW)
**Status:** OPEN  
**Current:** ILIKE on product name  
**Recommended:** 
- Enable pg_trgm extension
- Add GIN index for fuzzy search
- Consider Elasticsearch for advanced search

### 15. Image Optimization (LOW)
**Status:** OPEN  
**Current:** URLs stored directly  
**Recommended:** 
- CDN integration (CloudFront/Cloudinary)
- Automatic thumbnail generation
- WebP/AVIF conversion

## Monitoring & Observability Gaps

### 16. Application Metrics (MEDIUM)
**Status:** OPEN  
**Current:** Only `/health` endpoint  
**Recommended:** 
- Prometheus metrics endpoint
- Key metrics: request latency, error rate, payment success rate, order conversion

### 17. Distributed Tracing (LOW)
**Status:** OPEN  
**Current:** No tracing  
**Recommended:** OpenTelemetry + Jaeger/Zipkin

### 18. Log Aggregation (MEDIUM)
**Status:** OPEN  
**Current:** Console logging only  
**Recommended:** 
- Structured JSON logging
- ELK/Loki + Grafana
- Correlation IDs across requests

## Compliance & Legal

### 19. Privacy Policy / Terms of Service (MEDIUM)
**Status:** OPEN  
**Current:** Placeholder pages exist  
**Required:** Legal review for Indian market compliance

### 20. Data Retention Policy (LOW)
**Status:** OPEN  
**Current:** No automated deletion  
**Recommended:** 
- OTP codes: auto-expire (implemented)
- Inactive users: anonymize after 2 years
- Order data: retain 7 years for tax compliance

## Frontend-Specific

### 21. Mobile Responsiveness (LOW)
**Status:** UNKNOWN  
**Current:** Tailwind CSS responsive classes used  
**Required:** Test on actual mobile devices

### 22. Accessibility (LOW)
**Status:** UNKNOWN  
**Current:** Semantic HTML, ARIA labels in places  
**Required:** WCAG 2.1 AA audit

### 23. PWA Support (LOW)
**Status:** OPEN  
**Current:** Standard Vite/React app  
**Recommended:** Service worker, manifest, offline support

## Priority Matrix

| Priority | Count | Issues |
|----------|-------|--------|
| BLOCKER (External) | 3 | Razorpay, SMTP, Infrastructure |
| HIGH (Business) | 2 | Refresh tokens, CSRF |
| MEDIUM (Technical) | 8 | Email verification, password reset, pooling, caching, jobs, webhooks, metrics, logging |
| LOW (Polish) | 7 | Guest cart, audit, search, images, privacy, mobile, PWA |

## Recommended Next Steps
1. **Week 1:** Provision production infrastructure, configure Razorpay + SMTP
2. **Week 2:** Implement refresh token rotation, password reset flow
3. **Week 3:** Add Redis caching, Celery background jobs, webhook retry
4. **Week 4:** Monitoring setup (Prometheus/Grafana), log aggregation
5. **Week 5:** Legal review, accessibility audit, mobile testing
6. **Week 6:** Load testing, security penetration test, production deployment