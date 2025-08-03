from pydantic import BaseModel
from typing import Dict, Any, Optional

class ChatRequest(BaseModel):
    message: str
    context: Optional[Dict] = None

class ServiceNavigation(BaseModel):
    service_name: str
    display_name: str
    dashboard_route: str
    icon: str
    description: str

class ConfirmationRequired(BaseModel):
    required: bool = False
    action_type: str = ""  # "delete", "purge", "modify", etc.
    preview_data: Optional[Dict] = None
    warning_message: str = ""
    confirmation_text: str = ""

class ChatResponse(BaseModel):
    user_message: str
    selected_service: Optional[str] = None  # Ajout du champ manquant
    intent: Dict
    data: Any
    response: str
    success: bool
    error: Optional[str] = None
    is_markdown: Optional[bool] = True  # Ajout pour compatibilité
    service_navigation: Optional[ServiceNavigation] = None
    confirmation_required: Optional[ConfirmationRequired] = None
    action_id: Optional[str] = None

class ConfirmActionRequest(BaseModel):
    action_id: str
    confirmed: bool
    user_message: str

class ChatHealthResponse(BaseModel):
    status: str
    groq_available: bool
    services_available: Dict[str, bool]
    message: str