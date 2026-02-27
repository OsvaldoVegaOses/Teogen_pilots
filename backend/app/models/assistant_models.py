import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

AssistantBase = declarative_base()


class AssistantMessageLog(AssistantBase):
    __tablename__ = "assistant_message_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(64), nullable=False, index=True)
    mode = Column(String(20), nullable=False, default="public")
    user_id = Column(UUID(as_uuid=True), nullable=True)
    user_message = Column(Text, nullable=False)
    assistant_reply = Column(Text, nullable=False)
    intent = Column(String(64), nullable=False, default="general")
    blocked = Column(Boolean, nullable=False, default=False)
    client_ip = Column(String(128), nullable=True)
    user_agent = Column(String(512), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class AssistantContactLead(AssistantBase):
    __tablename__ = "assistant_contact_leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(64), nullable=False, index=True)
    source_mode = Column(String(20), nullable=False, default="public")
    user_id = Column(UUID(as_uuid=True), nullable=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    phone = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)
    consent = Column(Boolean, nullable=False, default=False)
    client_ip = Column(String(128), nullable=True)
    user_agent = Column(String(512), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
