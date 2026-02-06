from pydantic import BaseModel


class AIAdvisorRequest(BaseModel):
    user_prompt: str


class AIAdvisorResponse(BaseModel):
    summary: str
    advice: str
    raw_model_output: str
    is_data_fresh: bool = True
    last_successful_sync: str | None = None
    last_attempted_sync: str | None = None
    sync_status: str | None = None
    failure_reason: str | None = None
