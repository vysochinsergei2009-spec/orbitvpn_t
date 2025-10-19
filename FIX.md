After Ctrl + C combination (exit python3 run.py) appears an error:
'''
  File "asyncpg/protocol/protocol.pyx", line 608, in asyncpg.protocol.protocol.BaseProtocol.abort
  File "/usr/lib/python3.10/asyncio/sslproto.py", line 405, in abort
    self._ssl_protocol._abort()
  File "/usr/lib/python3.10/asyncio/sslproto.py", line 737, in _abort
    self._transport.abort()
  File "/usr/lib/python3.10/asyncio/selector_events.py", line 686, in abort
    self._force_close(None)
  File "/usr/lib/python3.10/asyncio/selector_events.py", line 737, in _force_close
    self._loop.call_soon(self._call_connection_lost, exc)
  File "/usr/lib/python3.10/asyncio/base_events.py", line 753, in call_soon
    self._check_closed()
  File "/usr/lib/python3.10/asyncio/base_events.py", line 515, in _check_closed
    raise RuntimeError('Event loop is closed')
RuntimeError: Event loop is closed
[2025-10-19 19:41:02,171] ERROR in sqlalchemy.pool.impl.AsyncAdaptedQueuePool: The garbage collector is trying to clean up non-checked-in connection <AdaptedConnection <asyncpg.connection.Connection object at 0x7fadff85cb80>>, which will be terminated.  Please ensure that SQLAlchemy pooled connections are returned to the pool explicitly, either by calling ``close()`` or by using appropriate context managers to manage their lifecycle.
sys:1: SAWarning: The garbage collector is trying to clean up non-checked-in connection <AdaptedConnection <asyncpg.connection.Connection object at 0x7fadff85cb80>>, which will be terminated.  Please ensure that SQLAlchemy pooled connections are returned to the pool explicitly, either by calling ``close()`` or by using appropriate context managers to manage their lifecycle.
'''