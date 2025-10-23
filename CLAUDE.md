# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OrbitVPN is a Telegram bot for managing VPN subscriptions built with:
- **aiogram 3.22.0** - Async Telegram bot framework
- **PostgreSQL + asyncpg** - Database with SQLAlchemy ORM
- **Redis** - Caching layer for performance optimization
- **Marzban** - VPN panel integration via aiomarzban
- **Payment Gateways** - TON cryptocurrency and Telegram Stars

The bot handles user subscriptions, VPN configuration management, payment processing, and referral rewards.

## Running the Application

### Start/Stop Commands
```bash
# Start the bot (mentioned in README)
boton.sh

# Stop the bot (mentioned in README)
botoff.sh

# Direct run (for development)
python run.py
```

### Environment Setup
Create a `.env` file with required credentials:
- `BOT_TOKEN` - Telegram bot token
- `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_NAME`, `DATABASE_HOST` - PostgreSQL credentials
- `REDIS_URL` - Redis connection string (default: redis://localhost)
- `S001_MARZBAN_USERNAME`, `S001_MARZBAN_PASSWORD`, `S001_BASE_URL` - Marzban panel credentials
- `TON_ADDRESS`, `TONAPI_URL`, `TONAPI_KEY` - TON payment gateway configuration
- `SUB_1M_PRICE`, `SUB_3M_PRICE`, `SUB_6M_PRICE`, `SUB_12M_PRICE` - Subscription pricing (overrides plans.json)

### Dependencies
Install with: `pip install -r requirements.txt`

## Architecture

### Entry Point
- `run.py` - Main entry point that initializes the bot, dispatcher, middlewares (locale, rate limiting), and starts polling

### Core Components

**app/core/**
- `handlers.py` - All bot command and callback handlers (start, payments, subscriptions, configs)
- `keyboards.py` - Inline keyboard layouts for user interactions

**app/repo/** - Repository pattern for data access
- `base.py` - BaseRepository with Redis integration
- `db.py` - Database session management and SQLAlchemy engine configuration
- `models.py` - SQLAlchemy models (User, Config, Payment, Server, TonTransaction, Promocode, Referral, MarzbanInstance)
- `user.py` - UserRepository for user operations, subscriptions, configs, balance (uses Redis caching)
- `marzban_client.py` - **NEW**: Multi-instance Marzban client with load balancing and node exclusion
- `server.py` - **DEPRECATED**: Old ServerRepository (use marzban_client.py instead)
- `client.py` - **DEPRECATED**: Old Marzban API wrapper (use marzban_client.py instead)
- `payments.py` - PaymentRepository for payment transactions

**app/payments/** - Payment processing system
- `manager.py` - PaymentManager orchestrates payment creation and confirmation
- `models.py` - Payment-related Pydantic models (PaymentMethod, PaymentResult)
- `gateway/base.py` - BasePaymentGateway abstract class
- `gateway/ton.py` - TonGateway for TON cryptocurrency payments
- `gateway/stars.py` - TelegramStarsGateway for Telegram Stars payments

**app/utils/**
- `redis.py` - Redis client initialization and connection management
- `rate_limit.py` - RateLimitMiddleware for anti-spam protection
- `logging.py` - Custom logger setup
- `txns_updater.py` - TonTransactionsUpdater polls TON blockchain for payment confirmations
- `rates.py` - Cryptocurrency rate fetching utilities

**app/locales/**
- `locales.py` - Translation strings for Russian and English
- `locales_mw.py` - LocaleMiddleware for multi-language support

### Database Schema
SQL files in `db/` directory:
- `uslist.sql`, `paymentlist.sql`, `trxnslist.sql`, `reflist.sql`, `servlist.sql`, `configslist.sql` - Database table queries

### Configuration
- `config.py` - Central configuration loading from environment variables and plans.json
- `plans.json` - Subscription plan definitions (days, prices)

## Key Architectural Patterns

### Repository Pattern
All database access goes through repository classes that extend `BaseRepository`. Repositories handle:
- Database queries via SQLAlchemy
- Redis caching with configurable TTLs
- Cache invalidation on mutations

### Redis Caching Strategy
Extensive Redis caching with keys like:
- `user:{tg_id}:balance` - User balance (TTL: REDIS_TTL)
- `user:{tg_id}:configs` - User VPN configs (TTL: REDIS_TTL)
- `user:{tg_id}:sub_end` - Subscription end timestamp (TTL: REDIS_TTL)
- `servers:best` - Best available server by load (TTL: 120s)

### Payment Flow
1. User initiates payment via `/add_funds` callback
2. PaymentManager creates payment record in database
3. For TON: User sends crypto with comment → TonTransactionsUpdater polls blockchain → confirms payment
4. For Stars: Telegram invoice → pre_checkout_query → successful_payment handler
5. Payment confirmation updates user balance and marks payment as processed

### VPN Config Management (NEW Multi-Instance System)
1. User requests config via `/add_config`
2. System checks active subscription status
3. **MarzbanClient** selects best instance and node:
   - Queries all active `MarzbanInstance` records
   - Fetches node metrics from each instance (users, traffic, usage_coefficient)
   - **Excludes nodes** listed in `excluded_node_names` array
   - Calculates load score for each node
   - Selects least loaded node across all instances
4. Creates Marzban user via `MarzbanClient.add_user()`
5. Stores config in database with VLESS link and instance_id
6. No manual server tracking - Marzban handles internally

### Middleware Stack
Order matters - applied in run.py:
1. LocaleMiddleware - Language detection and translation injection
2. RateLimitMiddleware - Anti-spam with custom limits per command

## Development Notes

### Logging Configuration
Set in config.py:
- `IS_LOGGING = True` - Enable/disable logging
- `LOG_LEVEL = "DEBUG"` - Set to "INFO", "DEBUG", or "ERROR"
- `LOG_AIOGRAM = False` - Toggle aiogram library logging

### Constants
- `FREE_TRIAL_DAYS = 7` - Free trial duration for new users
- `REFERRAL_BONUS = 50.0` - Bonus RUB for referrals
- `REDIS_TTL = 300` - Default Redis cache TTL (5 minutes)
- `TELEGRAM_STARS_RATE = 1.35` - Stars to RUB conversion
- `TON_RUB_RATE = 220` - TON to RUB rate (may be dynamic via rates.py)
- `PAYMENT_TIMEOUT_MINUTES = 10` - Payment expiration window

### State Management
FSM states defined in handlers.py:
- `PaymentState.waiting_amount` - Awaiting payment amount input
- `PaymentState.method` - Awaiting payment method selection

### Error Handling
- Handlers catch exceptions and log via `LOG.error()` with context
- User-facing errors return localized messages via translation keys
- Payment failures tracked with status: "pending", "confirmed", "failed"

### Testing
No test framework detected in the repository. When adding tests, consider:
- Mocking Redis and PostgreSQL connections
- Testing payment flows with fake blockchain transactions
- Testing rate limiting and locale middleware