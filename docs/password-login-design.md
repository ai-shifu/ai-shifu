# Password Login Feature Design

## 1. Overview

Add password login capability to AI-Shifu, allowing users to log in via **phone + password** or **email + password**.

### 1.1 User Scenarios

| Scenario | Flow |
|----------|------|
| New user registration (phone) | Enter phone → Get verification code → Verify → Set password → Done |
| New user registration (email) | Enter email → Get verification code → Verify → Set password → Done |
| Existing user sets password | Logged in → Account settings → Set password |
| Password login | Enter phone/email + password → Login |
| Forgot password | Enter phone/email → Get verification code → Verify → Reset password |
| Change password | Logged in → Enter old password + new password → Done |

## 2. Existing Architecture Analysis

### 2.1 Authentication Provider Pattern

The project uses a factory pattern to manage authentication methods:

- **Base class**: `src/api/flaskr/service/user/auth/base.py` → `AuthProvider`
- **Factory**: `src/api/flaskr/service/user/auth/factory.py` → `register_provider()` / `get_provider()`
- **Existing Providers**:
  - `phone` — Phone verification code login
  - `email` — Email verification code login (frontend marked as Coming Soon)
  - `google` — Google OAuth 2.0

### 2.2 Data Model

**`user_auth_credentials` table** (`AuthCredential` model):

| Field | Type | Description |
|-------|------|-------------|
| credential_bid | VARCHAR(32) | Business ID |
| user_bid | VARCHAR(32) | Associated user |
| provider_name | VARCHAR(255) | Auth provider (phone/email/google/**password**) |
| subject_id | VARCHAR(255) | Subject ID |
| subject_format | VARCHAR(255) | Subject format |
| identifier | VARCHAR(255) | Identifier (phone/email) |
| raw_profile | TEXT | Metadata JSON |
| password_hash | VARCHAR(255) | bcrypt password hash |
| state | INT | State (1201=unverified, 1202=verified) |

### 2.3 Frontend Structure

- Login page: `src/cook-web/src/app/login/page.tsx`
- Auth components: `src/cook-web/src/components/auth/`
- Environment config: `src/cook-web/src/config/environment.ts` → `loginMethodsEnabled`
- API layer: `src/cook-web/src/api/api.ts`

## 3. Technical Design

### 3.1 Database

**Approach: Use existing `AuthCredential` table with dedicated `password_hash` column**

New password credential record:
```
provider_name = "password"
identifier = "phone number" or "email"
subject_id = phone/email (same as identifier)
subject_format = "phone" or "email"
password_hash = "$2b$12$..."
state = 1202 (verified)
```

### 3.2 Backend New Files

#### `src/api/flaskr/service/user/password_utils.py`

Password utility functions:
- `hash_password(plain_text: str) -> str` — bcrypt hash, cost factor=12
- `verify_password(plain_text: str, hashed: str) -> bool` — Verify password
- `validate_password_strength(password: str) -> tuple[bool, str]` — Password strength check
  - Rules: minimum 8 characters, must contain letters and digits

#### `src/api/flaskr/service/user/auth/providers/password.py`

`PasswordAuthProvider` class:
- `provider_name = "password"`
- `supports_challenge = False`
- `verify(app, request)` — Find password credential from `AuthCredential`, verify hash

### 3.3 Backend API Endpoints

Added in `src/api/flaskr/route/user.py`:

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/user/set_password` | POST | Token required | Set password for logged-in user (first time only) |
| `/user/login_password` | POST | None | Login with phone/email + password |
| `/user/reset_password` | POST | None | Reset password via verification code |
| `/user/change_password` | POST | Token required | Change password (requires old password) |

#### Endpoint Details

**POST /user/set_password**
```json
// Request (requires login token)
{ "new_password": "newPassword123" }
// Response
{ "code": 0, "msg": "success" }
```
- User must be logged in (valid token required)
- Rejects if user already has a password (use change_password instead)
- Identifier taken from user's phone or email credential

**POST /user/login_password**
```json
// Request
{ "identifier": "13800138000", "password": "myPassword123" }
// Response
{ "code": 0, "data": { "token": "...", "user_info": {...} } }
```

**POST /user/reset_password**
```json
// Request
{ "identifier": "user@example.com", "code": "1234", "new_password": "newPassword123" }
// Response
{ "code": 0, "msg": "success" }
```

**POST /user/change_password**
```json
// Request (requires login token)
{ "old_password": "oldPass123", "new_password": "newPass456" }
// Response
{ "code": 0, "msg": "success" }
```

### 3.4 Frontend Changes

#### New: `src/cook-web/src/components/auth/PasswordLogin.tsx`

- **Login mode**: Phone/email input + password input + login button
- Password show/hide toggle
- Terms acceptance checkbox

#### Modified: `src/cook-web/src/app/login/page.tsx`

- `LoginMethod` type includes `'password'`
- `renderLoginContent` renders `PasswordLogin` component

#### Modified: `src/cook-web/src/config/environment.ts`

- `loginMethodsEnabled` supports `'password'` option

#### Modified: `src/cook-web/src/api/api.ts`

New API functions:
- `loginPassword(identifier, password)`
- `setPassword(password)`
- `resetPassword(identifier, code, password)`
- `changePassword(oldPassword, newPassword)`

### 3.5 Security

| Item | Approach |
|------|----------|
| Password storage | bcrypt, cost factor 12 |
| Password strength | ≥8 chars, must contain letters + digits |
| Brute force protection | Rate limiting after 5 failed attempts (future iteration) |
| Transport security | HTTPS (existing) |

> Note: Brute force protection (rate limiting/account lockout) is planned for a future iteration.

## 4. Out of Scope

- ❌ No changes to existing phone/email/google providers
- ❌ No changes to existing auth middleware (token validation unchanged)
- ❌ No login rate limiting/account lockout in first version

## 5. Dependencies

- Python: `bcrypt` package (added to requirements.txt)
- Frontend: No new dependencies
