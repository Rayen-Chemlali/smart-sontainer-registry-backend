from sqlalchemy import Column, String, Boolean, Text, JSON
from .base import BaseModel


class Rule(BaseModel):
    __tablename__ = "rules"

    # Identification
    name = Column(String(255), nullable=False)
    rule_type = Column(String(50), nullable=False)  # age_based, count_based, tag_based, size_based
    description = Column(Text)

    # Configuration
    conditions = Column(JSON, nullable=False)  # Conditions de la règle
    action = Column(String(50), default="delete", nullable=False)

    # Statut
    is_active = Column(Boolean, default=True)