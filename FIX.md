# Fixed Issues

## Issue 1 - FIXED: Callback Query Timeout (2025-10-22)
**Error**: `aiogram.exceptions.TelegramBadRequest: query is too old and response timeout expired or query ID is invalid`

**Solution**: All `callback.answer()` calls wrapped with `safe_answer_callback()` helper that ignores timeout errors.

---

## Issue 2 - NEW: Payment Error
[2025-10-22 17:08:25,574] ERROR in app.core.handlers: Payment error for user 7559373710: AttributeError: 'Message' object has no attribute 'message'