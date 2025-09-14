# -*- coding: utf-8 -*-
"""
데이터베이스 ORM 모델(테이블 스키마) 정의.

SQLAlchemy의 선언적 기반(declarative base)을 사용하여 데이터베이스 테이블 구조를 파이썬 클래스로 정의합니다.
"""
import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime
from .database import Base

class SignalLog(Base):
    """
    전략에 의해 생성된 매매 신호를 기록하는 테이블 모델.
    """
    __tablename__ = "signal_logs"
    __table_args__ = {'extend_existing': True} # 모델 재로드 시 발생할 수 있는 오류 방지

    id = Column(Integer, primary_key=True, index=True)
    # 타임스탬프 기본값: 데이터베이스 서버 시간이 아닌 UTC 시간 사용 (SQLite에서는 일반적)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    symbol = Column(String, index=True, nullable=False)
    strategy = Column(String)
    signal = Column(String, nullable=False)  # 'buy', 'sell', 'hold' 등

    def __repr__(self) -> str:
        return (
            f"<SignalLog(id={self.id}, "
            f"time='{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}', "
            f"symbol='{self.symbol}', signal='{self.signal}')>"
        )

class Trade(Base):
    """
    실제로 체결된 거래 내역을 기록하는 테이블 모델.
    """
    __tablename__ = "trades"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    symbol = Column(String, index=True, nullable=False)
    side = Column(String, nullable=False)  # 'buy' 또는 'sell'
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    pnl = Column(Float, nullable=True)  # 실현 손익 (선택적)

    def __repr__(self) -> str:
        return (
            f"<Trade(id={self.id}, "
            f"time='{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}', "
            f"symbol='{self.symbol}', side='{self.side}', "
            f"qty='{self.quantity}', price='{self.price}')>"
        )