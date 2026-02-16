from sqlalchemy import Column, String, Text, Boolean, Integer, ForeignKey, JSON, Float, DateTime, Enum, Table
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from .base import Base

# Many-to-Many link between codes and fragments
code_fragment_links = Table(
    "code_fragment_links",
    Base.metadata,
    Column("code_id", UUID(as_uuid=True), ForeignKey("codes.id", ondelete="CASCADE"), primary_key=True),
    Column("fragment_id", UUID(as_uuid=True), ForeignKey("fragments.id", ondelete="CASCADE"), primary_key=True),
    Column("confidence", Float, default=1.0)
)

class Project(Base):
    __tablename__ = "projects"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    methodological_profile = Column(String(50)) # 'straussian', 'constructivist', 'glaserian'
    language = Column(String(10), default="es")
    owner_id = Column(UUID(as_uuid=True)) # Linked to Entra ID sub/oid
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    interviews = relationship("Interview", back_populates="project", cascade="all, delete-orphan")
    codes = relationship("Code", back_populates="project", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="project", cascade="all, delete-orphan")
    memos = relationship("Memo", back_populates="project", cascade="all, delete-orphan")
    theories = relationship("Theory", back_populates="project", cascade="all, delete-orphan")

class Interview(Base):
    __tablename__ = "interviews"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    participant_pseudonym = Column(String(255))
    metadata_json = Column(JSON, default={})
    audio_blob_url = Column(Text)
    transcription_status = Column(String(20), default="pending")
    full_text = Column(Text)
    word_count = Column(Integer)
    language = Column(String(10))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="interviews")
    fragments = relationship("Fragment", back_populates="interview", cascade="all, delete-orphan")

class Fragment(Base):
    __tablename__ = "fragments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id = Column(UUID(as_uuid=True), ForeignKey("interviews.id", ondelete="CASCADE"))
    text = Column(Text, nullable=False)
    start_offset = Column(Integer)
    end_offset = Column(Integer)
    speaker_id = Column(String(50))
    embedding_synced = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    interview = relationship("Interview", back_populates="fragments")
    codes = relationship("Code", secondary=code_fragment_links, back_populates="fragments")

class Code(Base):
    __tablename__ = "codes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    label = Column(String(500), nullable=False)
    definition = Column(Text)
    code_type = Column(String(20), default="open") # 'open', 'axial', 'selective'
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"))
    created_by = Column(String(20), default="human") # 'human', 'ai', 'hybrid'
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="codes")
    category = relationship("Category", back_populates="codes")
    fragments = relationship("Fragment", secondary=code_fragment_links, back_populates="codes")

class Category(Base):
    __tablename__ = "categories"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    name = Column(String(500), nullable=False)
    definition = Column(Text)
    properties = Column(JSON, default=[])
    dimensions = Column(JSON, default=[])
    is_central = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="categories")
    codes = relationship("Code", back_populates="category")

class Memo(Base):
    __tablename__ = "memos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    title = Column(String(500))
    content = Column(Text, nullable=False)
    memo_type = Column(String(30)) # 'analytical', 'methodological', 'theoretical', 'reflexive'
    related_codes = Column(ARRAY(UUID(as_uuid=True)), default=[])
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="memos")

class Theory(Base):
    __tablename__ = "theories"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"))
    version = Column(Integer, default=1)
    central_category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"))
    model_json = Column(JSON, nullable=False)
    propositions = Column(JSON, default=[])
    validation = Column(JSON, default={})
    gaps = Column(JSON, default=[])
    confidence_score = Column(Float)
    status = Column(String(20), default="draft")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="theories")
