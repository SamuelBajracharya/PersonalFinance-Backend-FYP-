
from pydantic import BaseModel

class AIAdvisorRequest(BaseModel):
    user_prompt: str


class AIAdvisorResponse(BaseModel):
    summary: str
    advice: str
    raw_model_output: str
