from pydantic import BaseModel, Field


class PublicAssistantChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=64)


class PublicAssistantChatResponse(BaseModel):
    session_id: str
    reply: str
    blocked: bool
    intent: str
    logging_enabled: bool


class AssistantLeadCreateRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=5, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=1000)
    consent: bool


class AssistantLeadCreateResponse(BaseModel):
    created: bool
    logging_enabled: bool
    message: str


class AssistantMetricsResponse(BaseModel):
    logging_enabled: bool
    total_messages_7d: int
    blocked_messages_7d: int
    leads_7d: int


class AssistantMessageLogItem(BaseModel):
    session_id: str
    mode: str
    user_message: str
    assistant_reply: str
    intent: str
    blocked: bool
    created_at: str


class AssistantLeadItem(BaseModel):
    session_id: str
    source_mode: str
    name: str
    email: str
    company: str | None
    phone: str | None
    created_at: str


class AssistantOpsResponse(BaseModel):
    logging_enabled: bool
    recent_messages: list[AssistantMessageLogItem]
    recent_leads: list[AssistantLeadItem]
