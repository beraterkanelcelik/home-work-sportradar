# Security Review Report

## Summary

After a comprehensive security review of the codebase, **1 high-confidence vulnerability** was identified that requires attention.

---

# Vuln 1: CORS Origin Validation Bypass via Substring Matching

**File:** `backend/app/api/documents.py:444`

* **Severity:** Medium-High
* **Category:** CORS Misconfiguration
* **Confidence:** 8/10

**Description:**
The CORS origin validation at line 444 uses Python's `in` operator for substring matching instead of exact URL matching:

```python
if any(allowed in origin or allowed in referer for allowed in allowed_origins):
    response['Access-Control-Allow-Origin'] = origin if origin else 'http://localhost:3000'
    response['Access-Control-Allow-Credentials'] = 'true'
```

The `allowed in origin` check performs substring matching, meaning an attacker-controlled domain like `http://localhost:3000.attacker.com` would pass validation because the string `http://localhost:3000` is a substring of the malicious origin.

**Exploit Scenario:**
1. Attacker registers domain `localhost:3000.attacker.com`
2. Attacker hosts malicious page that makes cross-origin requests to the backend
3. Browser sends request with `Origin: http://localhost:3000.attacker.com`
4. Substring check passes (`'http://localhost:3000' in 'http://localhost:3000.attacker.com'` → True)
5. Server responds with `Access-Control-Allow-Origin: http://localhost:3000.attacker.com` and `Access-Control-Allow-Credentials: true`
6. Attacker's page can now make authenticated cross-origin requests to access user documents

**Recommendation:**
Replace substring matching with exact origin matching:

```python
if origin in allowed_origins:
    response['Access-Control-Allow-Origin'] = origin
    response['Access-Control-Allow-Credentials'] = 'true'
```

---

## Vulnerabilities Filtered as False Positives

The following potential vulnerabilities were investigated but determined to be false positives (confidence < 8):

| Finding | Reason for Exclusion | Confidence |
|---------|---------------------|------------|
| Path Traversal via Filename | Document ID comes from DB with owner validation; filename is display metadata only | 2/10 |
| JWT Token in Query Parameter | Industry-standard pattern for iframe/file preview; tokens are short-lived (5h) | 3/10 |
| Header Injection via Filename | Django 5.0 automatically validates headers and rejects CR/LF characters | 6/10 |
| Authorization Bypass in Fallback | Authorization check occurs before fallback; path is user-scoped | 1/10 |
| Tool Args Validation | Intentional HITL feature; edited args not used for execution | 3/10 |
| IDOR Race Condition | Single request atomicity; document_id is immutable during request | 2/10 |
| CSRF on API Endpoints | JWT token-based auth is CSRF-immune; @csrf_exempt is correct pattern | 2/10 |
