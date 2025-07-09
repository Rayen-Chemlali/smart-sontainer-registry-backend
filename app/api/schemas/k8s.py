from pydantic import BaseModel
from typing import List, Optional, Dict

class ContainerInfo(BaseModel):
    name: str
    image: str
    ready: bool

class PodResponse(BaseModel):
    name: str
    namespace: str
    status: str
    node: Optional[str]
    created: Optional[str]
    containers: List[ContainerInfo]

class DeploymentResponse(BaseModel):
    name: str
    namespace: str
    replicas: int
    ready_replicas: int
    available_replicas: int
    created: Optional[str]
    images: List[str]

class NamespaceResponse(BaseModel):
    name: str
    status: str
    created: Optional[str]