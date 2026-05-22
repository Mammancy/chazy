# CHAZY Backend Render Deployment

This backend is ready for Render Web Service deployment.

## Render settings

Build command:
```bash
pip install -r requirements.txt
```

Start command:
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Health check path:
```text
/api/v1/health
```

## Required environment variables

```env
APP_NAME=Chazy
APP_VERSION=0.1.0
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO
API_V1_PREFIX=/api/v1
DATABASE_URL=sqlite:///./chazy.db
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_RETRIES=2
OPENAI_RETRY_BASE_DELAY_SECONDS=0.5
CORS_ORIGINS=*
```

`OPENAI_API_KEY` can stay empty while testing fallback mode. When you buy a valid key, add it in Render Environment and restart the service.

## Test URLs after deploy

```text
https://YOUR-RENDER-SERVICE.onrender.com/api/v1/health
https://YOUR-RENDER-SERVICE.onrender.com/test-openai
```

Chat endpoint:
```text
POST https://YOUR-RENDER-SERVICE.onrender.com/api/v1/chat/
```

Example body:
```json
{
  "session_id": "android-local-session",
  "message": "i is happy today"
}
```



## SMTP email configuration

Set these Render environment variables to enable forgot-password email delivery:

```text
SMTP_HOST=smtp.your-provider.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=no-reply@your-domain.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
SMTP_TIMEOUT_SECONDS=20
PASSWORD_RESET_BASE_URL=https://your-frontend-or-app-reset-url
```

Notes:
- Use port `587` with `SMTP_USE_TLS=true` for most providers.
- Use port `465` with `SMTP_USE_SSL=true` and `SMTP_USE_TLS=false` if your provider requires SSL.
- Gmail requires an App Password, not your normal Gmail password.
