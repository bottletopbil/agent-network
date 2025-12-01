"""
FastAPI endpoints for Agent Registry.

Provides REST API for agent registration, search, and statistics.
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from marketplace.registry import AgentRegistry, AgentStatus, SearchFilters

# Initialize FastAPI app
app = FastAPI(title="Agent Registry API", version="1.0.0")

# Initialize registry (in production, use proper config)
REGISTRY_DB = Path(".state/registry.db")
REGISTRY_DB.parent.mkdir(parents=True, exist_ok=True)
registry = AgentRegistry(REGISTRY_DB)


# Request/Response models


class RegisterRequest(BaseModel):
    """Request to register an agent"""

    agent_id: str = Field(..., description="Unique agent identifier (DID)")
    manifest: dict = Field(
        ..., description="Agent manifest (capabilities, pricing, etc.)"
    )
    stake: float = Field(..., ge=0, description="Stake amount in credits")

    class Config:
        schema_extra = {
            "example": {
                "agent_id": "did:key:agent123",
                "manifest": {
                    "capabilities": ["code_analysis", "bug_detection"],
                    "pricing": {"base_rate": 10.0, "per_task": 5.0},
                    "tags": ["python", "security"],
                },
                "stake": 100.0,
            }
        }


class RegisterResponse(BaseModel):
    """Response from registration"""

    registration_id: str
    agent_id: str
    message: str


class UpdateManifestRequest(BaseModel):
    """Request to update agent manifest"""

    manifest: dict = Field(..., description="Updated manifest")


class SearchRequest(BaseModel):
    """Request to search agents"""

    capabilities: Optional[List[str]] = Field(None, description="Required capabilities")
    min_reputation: Optional[float] = Field(
        None, ge=0, le=1, description="Minimum reputation score"
    )
    max_price: Optional[float] = Field(None, ge=0, description="Maximum price")
    status: Optional[str] = Field(None, description="Agent status filter")
    tags: Optional[List[str]] = Field(None, description="Required tags")


class AgentRecord(BaseModel):
    """Agent record in search results"""

    agent_id: str
    manifest: dict
    stake: float
    status: str
    reputation_score: float
    total_tasks: int
    completed_tasks: int
    registered_at: float
    updated_at: float


class StatsResponse(BaseModel):
    """Agent statistics response"""

    agent_id: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    success_rate: float
    avg_response_time_ms: float
    total_earnings: float
    reputation_score: float
    last_active: float
    uptime_percentage: float


# API Endpoints


@app.post("/agents/register", response_model=RegisterResponse, status_code=201)
async def register_agent(request: RegisterRequest):
    """
    Register a new agent in the marketplace.

    Requires:
    - Unique agent_id (DID)
    - Manifest with capabilities and pricing
    - Minimum stake

    Returns registration ID on success.
    """
    try:
        registration_id = registry.register_agent(
            agent_id=request.agent_id, manifest=request.manifest, stake=request.stake
        )

        return RegisterResponse(
            registration_id=registration_id,
            agent_id=request.agent_id,
            message="Agent registered successfully",
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@app.put("/agents/{agent_id}/manifest")
async def update_manifest(agent_id: str, request: UpdateManifestRequest):
    """
    Update agent manifest.

    Allows agents to update their capabilities, pricing, and other metadata.
    """
    try:
        registry.update_manifest(agent_id, request.manifest)
        return {"agent_id": agent_id, "message": "Manifest updated successfully"}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")


@app.get("/agents/search", response_model=List[AgentRecord])
async def search_agents(
    capabilities: Optional[str] = Query(
        None, description="Comma-separated capabilities"
    ),
    min_reputation: Optional[float] = Query(None, ge=0, le=1),
    status: Optional[str] = Query(None),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
):
    """
    Search for agents by capabilities and filters.

    Returns list of matching agents ordered by reputation.
    """
    try:
        # Parse comma-separated lists
        cap_list = capabilities.split(",") if capabilities else None
        tag_list = tags.split(",") if tags else None

        # Create filters
        filters = SearchFilters(
            min_reputation=min_reputation,
            status=AgentStatus(status) if status else None,
            tags=tag_list,
        )

        # Search
        results = registry.search_agents(capabilities=cap_list, filters=filters)

        return [AgentRecord(**result) for result in results]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/agents/{agent_id}/stats", response_model=StatsResponse)
async def get_agent_stats(agent_id: str):
    """
    Get statistics for a specific agent.

    Returns performance metrics, earnings,and reputation.
    """
    try:
        stats = registry.get_agent_stats(agent_id)

        if stats is None:
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

        return StatsResponse(
            agent_id=stats.agent_id,
            total_tasks=stats.total_tasks,
            completed_tasks=stats.completed_tasks,
            failed_tasks=stats.failed_tasks,
            success_rate=stats.success_rate,
            avg_response_time_ms=stats.avg_response_time_ms,
            total_earnings=stats.total_earnings,
            reputation_score=stats.reputation_score,
            last_active=stats.last_active,
            uptime_percentage=stats.uptime_percentage,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "agent-registry"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
