import asyncio
import logging
from typing import Set
from app.payments.manager import PaymentManager
from app.payments.models import PaymentMethod

LOG = logging.getLogger(__name__)

class PaymentWatcher:
    
    def __init__(self, interval: int = 60):
        self.manager = PaymentManager()
        self.interval = interval
        self.running = False
        self._task = None
        self._processing: Set[int] = set()

    async def start(self):
        if self.running:
            LOG.warning("Watcher already running")
            return
        
        self.running = True
        self._task = asyncio.create_task(self._watch_loop())
        LOG.info("Payment watcher started")

    async def stop(self):
        if not self.running:
            return
        
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        await self.manager.close()
        LOG.info("Payment watcher stopped")

    async def _watch_loop(self):
        while self.running:
            try:
                await self._check_pending_payments()
            except Exception as e:
                LOG.error(f"Watcher error: {e}", exc_info=True)
            
            await asyncio.sleep(self.interval)

    async def _check_pending_payments(self):
        polling_methods = [
            method for method, gateway in self.manager.gateways.items()
            if gateway.requires_polling
        ]
        
        for method in polling_methods:
            try:
                payments = await self.manager.get_pending_payments(method)
                
                for payment in payments:
                    payment_id = payment['id']
                    
                    if payment_id in self._processing:
                        continue
                    
                    self._processing.add(payment_id)
                    try:
                        await self.manager.check_payment(payment_id)
                    finally:
                        self._processing.discard(payment_id)
                        
            except Exception as e:
                LOG.error(f"Check {method} payments error: {e}")