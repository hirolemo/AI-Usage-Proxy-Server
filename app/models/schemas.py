from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime


# Chat Completion Models (OpenAI-compatible)
class ImageUrl(BaseModel):
    url: str


class ContentPart(BaseModel):
    type: Literal["text", "image_url"]
    text: str | None = None
    image_url: ImageUrl | None = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str | list[ContentPart]


class StreamOptions(BaseModel):
    include_usage: bool = True


class ResponseFormat(BaseModel):
    type: Literal["text", "json_object"] = "text"


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: str | list[str] | None = None
    stream_options: StreamOptions | None = None
    response_format: ResponseFormat | None = None
    # Unsupported fields (for warnings)
    tools: list | None = None
    tool_choice: str | dict | None = None
    logprobs: bool | None = None
    logit_bias: dict | None = None


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class Choice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage | None = None


# Streaming response models
class DeltaMessage(BaseModel):
    role: str | None = None
    content: str | None = None


class StreamChoice(BaseModel):
    index: int
    delta: DeltaMessage
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[StreamChoice]
    usage: Usage | None = None


# User and Admin Models
class UserCreate(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100)


class UserResponse(BaseModel):
    user_id: str
    api_key: str
    created_at: datetime | None = None


class UserListResponse(BaseModel):
    users: list[UserResponse]


class RateLimitUpdate(BaseModel):
    requests_per_minute: int | None = None
    requests_per_day: int | None = None
    tokens_per_minute: int | None = None
    tokens_per_day: int | None = None
    total_token_limit: int | None = None


class RateLimitResponse(BaseModel):
    user_id: str
    requests_per_minute: int | None
    requests_per_day: int | None
    tokens_per_minute: int | None
    tokens_per_day: int | None
    total_token_limit: int | None


# Usage Models
class ModelUsage(BaseModel):
    total_tokens: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    request_count: int
    total_cost: float = 0.0


class UsageResponse(BaseModel):
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    request_count: int
    total_cost: float = 0.0
    by_model: dict[str, ModelUsage]


class UsageSummary(BaseModel):
    user_id: str
    usage: UsageResponse
    rate_limits: RateLimitResponse | None


# Error Models
class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


class RateLimitError(BaseModel):
    error: str = "rate_limit_exceeded"
    message: str
    retry_after: int | None = None


# Pricing Models
class ModelPricingCreate(BaseModel):
    model: str = Field(..., min_length=1)
    input_cost_per_million: float = Field(..., ge=0.0)
    output_cost_per_million: float = Field(..., ge=0.0)


class ModelPricingResponse(BaseModel):
    model: str
    input_cost_per_million: float
    output_cost_per_million: float
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ModelPricingListResponse(BaseModel):
    pricing: list[ModelPricingResponse]


class PricingHistoryEntry(BaseModel):
    id: int
    model: str
    input_cost_per_million: float
    output_cost_per_million: float
    changed_by: str
    changed_at: datetime


class PricingHistoryResponse(BaseModel):
    history: list[PricingHistoryEntry]
