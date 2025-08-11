from pydantic import BaseModel
from typing import List, Optional, Dict, Any

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

class PodListResponse(BaseModel):
    namespace: str
    pods: List[PodResponse]
    total_count: int
    status_summary: Dict[str, int]
    images_used: List[str]

class DeploymentResponse(BaseModel):
    name: str
    namespace: str
    replicas: int
    ready_replicas: int
    available_replicas: int
    created: Optional[str]
    images: List[str]

class DeploymentListResponse(BaseModel):
    namespace: str
    deployments: List[DeploymentResponse]
    total_count: int
    ready_count: int
    images_used: List[str]

class NamespaceResponse(BaseModel):
    name: str
    status: str
    created: Optional[str]

class ServicePortInfo(BaseModel):
    port: int
    target_port: Optional[str]
    protocol: str

class ServiceResponse(BaseModel):
    name: str
    namespace: str
    type: str
    cluster_ip: str
    ports: List[ServicePortInfo]
    created: Optional[str]

class ServiceListResponse(BaseModel):
    namespace: str
    services: List[ServiceResponse]
    total_count: int
    service_types: List[str]
    exposed_ports: List[ServicePortInfo]

class DeployedImagesResponse(BaseModel):
    images: List[str]
    total_count: int
    namespace: str
    unique_registries: List[str]

class NamespaceStats(BaseModel):
    name: str
    pods_count: int
    deployments_count: int
    services_count: int

class ClusterSummary(BaseModel):
    total_namespaces: int
    user_namespaces: int
    total_pods: int
    total_deployments: int
    total_services: int
    unique_images: int
    registries: List[str]

class HealthIndicators(BaseModel):
    namespaces_accessible: int
    images_diversity: int
    avg_pods_per_namespace: float

class ClusterOverviewResponse(BaseModel):
    cluster_summary: ClusterSummary
    namespace_details: List[NamespaceStats]
    health_indicators: HealthIndicators

class ResourceSearchResult(BaseModel):
    name: str
    namespace: str
    matching_image: str


class ImageSearchResponse(BaseModel):
    search_term: str
    search_scope: str
    matching_pods: List[Dict[str, Any]]
    matching_deployments: List[Dict[str, Any]]
    total_matches: int
    unique_images_found: List[str]