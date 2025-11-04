#!/bin/bash

# Script to switch YooKassa between TEST and PRODUCTION modes

MODE=$1

if [ -z "$MODE" ]; then
    echo "Usage: $0 [test|prod]"
    echo ""
    echo "Current mode:"
    grep "YOOKASSA_TESTNET=" .env
    exit 1
fi

if [ "$MODE" == "test" ]; then
    sed -i 's/^YOOKASSA_TESTNET=.*/YOOKASSA_TESTNET=true/' .env
    echo "✓ Switched to TEST mode (using test shop credentials)"
    echo ""
    echo "Test shop will be used for all payments"
    echo "Remember to restart the bot: ./botoff.sh && ./boton.sh"
elif [ "$MODE" == "prod" ]; then
    sed -i 's/^YOOKASSA_TESTNET=.*/YOOKASSA_TESTNET=false/' .env
    echo "✓ Switched to PRODUCTION mode (using live shop credentials)"
    echo ""
    echo "⚠️  WARNING: Real money will be processed!"
    echo "Remember to restart the bot: ./botoff.sh && ./boton.sh"
else
    echo "Invalid mode: $MODE"
    echo "Use 'test' or 'prod'"
    exit 1
fi
