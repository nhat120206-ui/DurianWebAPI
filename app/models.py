from sqlalchemy import (
    Column, Integer, BigInteger, String, Unicode, Float, Boolean, DateTime,
    ForeignKey, Numeric, SmallInteger
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class NguoiDung(Base):
    __tablename__ = "NguoiDung"
    user_id = Column(Integer, primary_key=True, index=True)
    full_name = Column(Unicode(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="User", nullable=False)
    created_at = Column(DateTime, server_default=func.sysdatetime())
    is_active = Column(Boolean, default=True, nullable=False)


class PhienBanMoHinh(Base):
    __tablename__ = "PhienBanMoHinh"
    model_id = Column(Integer, primary_key=True, index=True)
    model_name = Column(Unicode(100), nullable=False)
    version = Column(String(30), nullable=False)
    model_path = Column(Unicode(500), nullable=False)
    created_at = Column(DateTime, server_default=func.sysdatetime())
    accuracy = Column(Float, nullable=True)
    f1_score = Column(Float, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)

    training_data = relationship(
        "DuLieuHuanLuyen",
        back_populates="model_version",
        uselist=False,
        cascade="all, delete-orphan"
    )


class DuLieuHuanLuyen(Base):
    __tablename__ = "DuLieuHuanLuyen"
    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(
        Integer,
        ForeignKey("PhienBanMoHinh.model_id"),
        unique=True,
        nullable=False
    )
    file_size = Column(BigInteger, nullable=True)
    file_format = Column(String(10), nullable=False)
    source = Column(Unicode(255), nullable=True)
    description = Column(Unicode(255), nullable=True)
    created_at = Column(DateTime, server_default=func.sysdatetime())

    model_version = relationship("PhienBanMoHinh", back_populates="training_data")


class Benh(Base):
    __tablename__ = "Benh"
    disease_id = Column(Integer, primary_key=True, index=True)
    disease_name = Column(Unicode(150), unique=True, nullable=False)
    class_key = Column(String(50), nullable=True)
    symptoms = Column(Unicode(), nullable=True)
    description = Column(Unicode(), nullable=True)
    treatments = relationship(
        "BienPhap", back_populates="disease",
        cascade="all, delete-orphan"
    )


class BienPhap(Base):
    __tablename__ = "BienPhap"
    treatment_id = Column(Integer, primary_key=True, index=True)
    disease_id = Column(Integer, ForeignKey("Benh.disease_id"), nullable=False)
    treatment_name = Column(Unicode(200), nullable=False)
    treatment_type = Column(Unicode(30), nullable=True)
    description = Column(Unicode(), nullable=True)
    prevention = Column(Unicode(), nullable=True)
    disease = relationship("Benh", back_populates="treatments")


class ChanDoan(Base):
    __tablename__ = "ChanDoan"
    diagnosis_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("NguoiDung.user_id"), nullable=False)
    model_id = Column(Integer, ForeignKey("PhienBanMoHinh.model_id"), nullable=False)
    image_path = Column(Unicode(500), nullable=False)
    diagnosis_date = Column(DateTime, server_default=func.sysdatetime())
    status = Column(String(20), default="Pending", nullable=False)
    is_uncertain = Column(Boolean, default=False, nullable=False)
    processing_time_ms = Column(Integer, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    actual_disease_id = Column(Integer, ForeignKey("Benh.disease_id"), nullable=True)
    results = relationship(
        "KetQuaChanDoan", back_populates="diagnosis",
        cascade="all, delete-orphan"
    )


class KetQuaChanDoan(Base):
    __tablename__ = "KetQuaChanDoan"
    result_id = Column(Integer, primary_key=True, index=True)
    diagnosis_id = Column(
        Integer, ForeignKey("ChanDoan.diagnosis_id", ondelete="CASCADE"),
        nullable=False
    )
    disease_id = Column(Integer, ForeignKey("Benh.disease_id"), nullable=False)
    rank_no = Column(SmallInteger, nullable=False)
    confidence_score = Column(Numeric(5, 4), nullable=False)
    diagnosis = relationship("ChanDoan", back_populates="results")
    disease = relationship("Benh")