# YooKassa Payment Gateway Setup

## Overview

YooKassa payment gateway has been successfully integrated into OrbitVPN bot. This allows users to pay for VPN subscriptions using bank cards, e-wallets, and other payment methods supported by YooKassa.

## Implementation Details

### Files Created/Modified

1. **New Gateway Implementation:**
   - `app/payments/gateway/yookassa.py` - YooKassa payment gateway class

2. **Updated Files:**
   - `app/payments/models.py` - Added `YOOKASSA` to `PaymentMethod` enum
   - `app/payments/manager.py` - Registered YooKassa gateway and added polling support
   - `app/core/keyboards.py` - Added YooKassa button to payment methods keyboard
   - `app/core/handlers/payments.py` - Added YooKassa payment handler
   - `app/locales/locales.py` - Added Russian and English translations for YooKassa
   - `config.py` - Added `YOOKASSA_SHOP_ID` and `YOOKASSA_SECRET_KEY` configuration
   - `requirements.txt` - Added `yookassa` library dependency

## Configuration Steps

### 1. Get YooKassa Credentials

1. Register at https://yookassa.ru/
2. Create a shop/merchant account
3. Go to Settings → API Keys
4. Copy your **Shop ID** and **Secret Key**

### 2. Configure Environment Variables

Add the following to your `.env` file:

```bash
# YooKassa Payment Gateway Configuration

# Production credentials (live payments with real money)
YOOKASSA_SHOP_ID=your_production_shop_id
YOOKASSA_SECRET_KEY=your_production_secret_key

# Test credentials (separate test shop for safe testing)
YOOKASSA_TEST_SHOP_ID=your_test_shop_id
YOOKASSA_TEST_SECRET_KEY=your_test_secret_key

# Mode selector (set to 'true' for testing, 'false' for production)
YOOKASSA_TESTNET=true
```

**Production Example:**
```bash
YOOKASSA_SHOP_ID=123456
YOOKASSA_SECRET_KEY=live_ABC123XYZ456...
YOOKASSA_TEST_SHOP_ID=789012
YOOKASSA_TEST_SECRET_KEY=test_DEF789GHI012...
YOOKASSA_TESTNET=false  # Use production shop
```

**Test Mode Example:**
```bash
YOOKASSA_SHOP_ID=123456
YOOKASSA_SECRET_KEY=live_ABC123XYZ456...
YOOKASSA_TEST_SHOP_ID=789012
YOOKASSA_TEST_SECRET_KEY=test_DEF789GHI012...
YOOKASSA_TESTNET=true  # Use test shop
```

### 3. Install Dependencies

The `yookassa` library is already added to `requirements.txt`. If you need to reinstall:

```bash
source venv/bin/activate
pip install yookassa
```

### 4. Restart the Bot

```bash
./botoff.sh
./boton.sh
```

## How It Works

### Payment Flow

1. **User Initiates Payment:**
   - User clicks "Add Funds" → Selects "YooKassa"
   - Selects amount (200, 500, 1000 RUB or custom)

2. **Payment Creation:**
   - Bot creates payment via YooKassa API
   - Generates unique payment URL with redirect confirmation
   - Returns URL to user with "Pay" button

3. **User Pays:**
   - User clicks "Pay" button
   - Opens YooKassa payment page in browser
   - Completes payment using bank card, wallet, etc.

4. **Payment Confirmation:**
   - Bot polls YooKassa API every 60 seconds for pending payments
   - When payment status changes to "succeeded", bot:
     - Updates payment status in database
     - Credits user balance
     - Invalidates Redis cache
     - Sends confirmation message to user

### Security Features

- **Database Locks:** Uses `SELECT FOR UPDATE` to prevent race conditions
- **Transaction Hash Validation:** Prevents duplicate confirmations
- **Atomic Updates:** Balance and payment status updated in single transaction
- **Metadata Tracking:** Payment ID and user ID stored in YooKassa metadata

### Supported Features

- ✅ Redirect payment confirmation (user pays on YooKassa website)
- ✅ Automatic payment polling (60-second intervals)
- ✅ Payment cancellation
- ✅ Custom amounts (200-100,000 RUB)
- ✅ Multi-language support (Russian/English)
- ✅ Redis caching for performance
- ✅ Database transaction safety

## Testing

### Test Mode

YooKassa provides a test environment. To use it:

1. Get test credentials from YooKassa dashboard
2. Use test Shop ID and Secret Key in `.env`
3. Use test bank card numbers provided by YooKassa

### Test Cards (YooKassa Test Environment)

- **Successful payment:** `5555 5555 5555 4477` (any CVV, any future expiry)
- **Failed payment:** `5555 5555 5555 4444`

## Troubleshooting

### Payment Not Confirming

1. Check YooKassa credentials in `.env`
2. Verify bot has internet access to YooKassa API
3. Check logs: `tail -f logs/bot.log` (if logging enabled)
4. Ensure payment status is "pending" in database

### Import Errors

If you see `ModuleNotFoundError: No module named 'yookassa'`:

```bash
source venv/bin/activate
pip install yookassa
```

### Payment Polling Not Working

The polling loop starts automatically when:
- A TON, CryptoBot, or YooKassa payment is created
- Runs every 60 seconds while pending payments exist
- Stops when no pending payments remain

## API Rate Limits

YooKassa API has rate limits. The bot handles this by:
- Polling only when pending payments exist
- Using 60-second intervals (not too frequent)
- Stopping polling when queue is empty

## Production Recommendations

1. **Use HTTPS:** YooKassa requires HTTPS for production webhooks (future enhancement)
2. **Monitor Logs:** Enable logging to track payment issues
3. **Set Limits:** Adjust `PAYMENT_TIMEOUT_MINUTES` in `config.py` if needed
4. **Backup Database:** Payment records are critical for accounting

## Future Enhancements

Possible improvements:

- [ ] Webhook support (instant confirmation instead of polling)
- [ ] Payment receipts (fiscal compliance for Russia)
- [ ] Refund functionality
- [ ] Payment analytics dashboard
- [ ] Multi-currency support

## Support

For YooKassa-specific issues:
- Documentation: https://yookassa.ru/developers/api
- Support: https://yookassa.ru/help

For bot integration issues:
- Check CLAUDE.md for architecture details
- Review logs in production environment
