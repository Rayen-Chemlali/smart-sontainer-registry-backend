from pydantic import BaseModel
from typing import Dict, Any, Optional

class ChatRequest(BaseModel):
    message: str
    context: Optional[Dict] = None

class ChatResponse(BaseModel):
    user_message: str
    intent: Dict
    data: Any
    response: str
    success: bool
    error: Optional[str] = None

class ChatHealthResponse(BaseModel):
    status: str
    groq_available: bool
    services_available: Dict[str, bool]
    message: str