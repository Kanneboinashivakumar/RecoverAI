from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.policies import router as policies_router
from app.api.dashboard import router as dashboard_router
from app.api.transactions import router as transactions_router
from app.api.agent_replay import router as agent_replay_router
from app.api.experiments import router as experiments_router
from app.api.policy_center import router as policy_center_router

app = FastAPI(title="RecoverAI")

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(policies_router, prefix="/api/policies", tags=["policies"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(transactions_router, prefix="/api/transactions", tags=["transactions"])
app.include_router(agent_replay_router, prefix="/api/agent-replay", tags=["agent-replay"])
app.include_router(experiments_router, prefix="/api/experiments", tags=["experiments"])
app.include_router(policy_center_router, prefix="/api/policy-center", tags=["policy-center"])
