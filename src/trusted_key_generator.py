"""HTTP boundary for the Trusted Key Generator (TKG)."""

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


_IPFE_DIR = Path(__file__).resolve().parent.parent / "ipfe_resource_ranking"
if str(_IPFE_DIR) not in sys.path:
    sys.path.insert(0, str(_IPFE_DIR))

from private_protocol import TrustedKeyGenerator
from trust_store import TrustStore


class JobRequest(BaseModel):
    job_id: str
    qos_priority: dict[str, float]
    bounds: dict[str, tuple[float, float]] | None = None
    value_scale: int = Field(default=1000, gt=0)
    weight_scale: int = Field(default=10, gt=0)


class RankRequest(BaseModel):
    encrypted_offers: dict[str, dict]
    combinations: list[list[str]]
    offer_owners: dict[str, str]


app = FastAPI(title="Trusted IPFE Key Generator")
tkg = TrustedKeyGenerator()
trust_store = TrustStore()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/jobs")
def issue_job(request: JobRequest):
    try:
        return tkg.issue_job(
            request.job_id,
            request.qos_priority,
            bounds=request.bounds,
            value_scale=request.value_scale,
            weight_scale=request.weight_scale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/jobs/{job_id}/rank")
def rank_job(job_id: str, request: RankRequest):
    try:
        if set(request.offer_owners) != set(request.encrypted_offers):
            raise ValueError("Every encrypted offer must have exactly one owner")
        if any(not owner for owner in request.offer_owners.values()):
            raise ValueError("Offer owners must be nonempty")
        trust_by_owner = {
            owner: trust_store.get_trust_score(owner, default=1.0)
            for owner in set(request.offer_owners.values())
        }
        trusted_values = {
            offer_id: {"reliability": trust_by_owner[owner]}
            for offer_id, owner in request.offer_owners.items()
        }
        return tkg.rank_combinations(
            job_id,
            request.encrypted_offers,
            request.combinations,
            trusted_values=trusted_values,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
