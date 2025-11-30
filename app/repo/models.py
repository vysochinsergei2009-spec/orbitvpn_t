from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime, Numeric, Float, Text, CHAR, ARRAY, JSON
)
from .db import Base
from datetime import datetime

class Config(Base):
    __tablename__ = "configs"
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, index=True)
    name = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    vless_link = Column(String)
    server_id = Column(String)
    username = Column(String)
    deleted = Column(Boolean, default=False)

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger)
    method = Column(String)
    amount = Column(Numeric)
    currency = Column(String)
    status = Column(String)
    comment = Column(Text)
    tx_hash = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)  # Payment expiration time
    expected_crypto_amount = Column(Numeric, nullable=True)
    extra_data = Column(JSON, nullable=True)  # For storing extra data like CryptoBot invoice_id

class Referral(Base):
    __tablename__ = "referrals"
    id = Column(BigInteger, primary_key=True)
    inviter_id = Column(BigInteger)
    invited_id = Column(BigInteger)
    invite_code = Column(Text)
    created_at = Column(DateTime)
    reward_given = Column(Boolean)
    reward_amount = Column(Float)
    note = Column(Text)

class MarzbanInstance(Base):
    __tablename__ = "marzban_instances"
    id = Column(String, primary_key=True)  # e.g., "s001", "s002"
    name = Column(String)  # Friendly name
    base_url = Column(Text, nullable=False)  # Marzban panel URL
    username = Column(Text, nullable=False)  # Marzban login
    password = Column(Text, nullable=False)  # Marzban password
    is_active = Column(Boolean, default=True)  # Enable/disable instance
    priority = Column(Integer, default=100)  # Lower = higher priority
    excluded_node_names = Column(ARRAY(String), default=[])  # Node names to exclude from load balancing
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Server(Base):
    """
    DEPRECATED: Use MarzbanInstance instead.
    Kept for backward compatibility with existing data.
    """
    __tablename__ = "servers"
    id = Column(String, primary_key=True)
    country = Column(String)
    ip = Column(String)
    ram = Column(Integer)
    volume = Column(Integer)
    users_count = Column(Integer)
    base_url = Column(Text)
    load_avg = Column(Float)
    login = Column(Text)
    password = Column(Text)
    updated_at = Column(DateTime)

class TonTransaction(Base):
    __tablename__ = "ton_transactions"
    tx_hash = Column(Text, primary_key=True)
    amount = Column(Numeric)
    comment = Column(Text)
    sender = Column(String)
    created_at = Column(DateTime)
    processed_at = Column(DateTime, nullable=True)

class User(Base):
    __tablename__ = "users"
    tg_id = Column(BigInteger, primary_key=True)
    balance = Column(Numeric, default=0)
    subscription_end = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    username = Column(Text)
    lang = Column(String, default="ru")
    configs = Column(Integer, default=0)
    referrer_id = Column(BigInteger)
    first_buy = Column(Boolean, default=True)
    notifications = Column(Boolean, default=True)