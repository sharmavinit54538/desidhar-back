# DesiDhar Auth Backend

## Quick Start (Windows cmd)

```cmd
REM 1. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

REM 2. Install dependencies
pip install -r requirements.txt

REM 3. Configure environment
copy .env.example .env
REM Edit .env with your DATABASE_URL and SECRET_KEY

REM 4. Create PostgreSQL database
createdb desidhar

REM 5. Run migrations
alembic upgrade head

REM 6. Create admin user
python -m scripts.create_admin admin

REM 7. Run server
uvicorn app.main:app --reload
```

## Local frontend and CORS

The frontend runs on port `8080`. The default CORS allow-list includes
`http://localhost:8080` and `http://127.0.0.1:8080`.
If you open the frontend through Vite's Network URL, add that exact origin
(scheme, IP address, and port, without a trailing slash) to `CORS_ORIGINS` in `.env`.
Restart Uvicorn after editing `.env`; environment file changes alone may not
trigger its reload. A missing frontend origin causes `OPTIONS /auth/otp/request`
to return `400 Disallowed CORS origin` before the OTP endpoint is called.

## API Endpoints

### Customer (OTP)
- `POST /auth/otp/request` - Request OTP
- `POST /auth/otp/verify` - Verify OTP, get JWT

### Admin (Password)
- `POST /admin/auth/login` - Login with username/password

### Authenticated
- `GET /me` - Current user info
- `GET /admin/ping` - Admin only (403 for customers)
