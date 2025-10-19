from sqlalchemy import (
    Column, Integer, BigInteger, String, Boolean, DateTime, Numeric, Float, Text, CHAR
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
    expected_crypto_amount = Column(Numeric, nullable=True)

class PromocodeUsage(Base):
    __tablename__ = "promocode_usages"
    id = Column(BigInteger, primary_key=True)
    promocode_id = Column(BigInteger)
    tg_id = Column(BigInteger)
    activated_at = Column(DateTime)

class Promocode(Base):
    __tablename__ = "promocodes"
    id = Column(BigInteger, primary_key=True)
    code = Column(Text)
    description = Column(Text)
    created_at = Column(DateTime)
    expires_at = Column(DateTime)
    usage_limit = Column(Integer)
    used_count = Column(Integer)
    reward_type = Column(Text)
    reward_value = Column(Numeric)
    creator_id = Column(BigInteger)
    active = Column(Boolean)

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

class Server(Base):
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
    user_ip = Column(Text)
    balance = Column(Numeric, default=0)
    plan = Column(Text)
    subscription_end = Column(DateTime)
    traffic_used = Column(BigInteger, default=0)
    max_traffic = Column(BigInteger, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    username = Column(Text)
    lang = Column(String, default="ru")
    configs = Column(Integer, default=0)
    referrer_id = Column(BigInteger)
    first_buy = Column(Boolean, default=True)