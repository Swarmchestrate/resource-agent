"""Integration test for the complete private-ranking protocol workflow."""

import asyncio
import json
import logging
import random
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


pytest.importorskip("mife")
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "ipfe_resource_ranking"))

import ra_base
import trusted_key_generator as tkg_service
from private_protocol import TrustedKeyGenerator
from ra_base import ResourceAgent


class FakeTosca:
    def get_qos(self):
        return {
            "reliability": 1,
            "energy": 1,
            "bandwidth": 1,
            "price": 1,
        }


class FakeTrustStore:
    def __init__(self):
        self.lookups = []

    def get_trust_score(self, owner, default=1.0):
        self.lookups.append(owner)
        return {"Hub-RA": 0.2, "Worker-RA": 0.9}.get(owner, default)


class FakeCapacityRegistry:
    def __init__(self, offers):
        self.offers = deepcopy(offers)
        self.accepted = []
        self.rejected = []

    def dump_capacity_registry_info(self):
        return None

    def resource_offer_generate_from_SAT_file(self, job_id, ask_yaml):
        return deepcopy(self.offers)

    def resource_offer_query_all(self, job_id):
        return deepcopy(self.offers)

    def resource_offer_accept(self, offer_id, offer):
        self.accepted.append(offer_id)

    def resource_offer_reject(self, offer_id, offer):
        self.rejected.append(offer_id)


class InProcessBus:
    """Synchronous P2P test double that dispatches actual RA handlers."""

    def __init__(self):
        self.agents = {}
        self.messages = []

    def endpoint(self, owner):
        bus = self

        class Endpoint:
            peer_id = owner

            def find_peers(self, filters):
                return [ra_id for ra_id in bus.agents if ra_id != owner]

            def send(self, target, message_type, message):
                payload = deepcopy(message)
                bus.messages.append((owner, target, message_type, payload))
                if message_type == "MSG_RESOURCE_RESPONSE":
                    bus.agents[target]._handle_resource_response(owner, payload)
                elif message_type == "MSG_SELECTED_OFFER":
                    bus.agents[target]._handle_selected_offer(owner, payload)

        return Endpoint()


def make_offer(ra_id, microservice, quality):
    offer_id = f"{ra_id.lower()}-{microservice}"
    return offer_id, {
        "ids": {
            "ra_id": ra_id,
            "res_id": f"{ra_id.lower()}-capacity",
            "res_type": "edge",
            "offer_id": offer_id,
            "provider_id": ra_id.lower(),
        },
        "properties": {"microservice": microservice},
        "characteristics": {
            "energy.consumption": quality["energy"],
            "host.bandwidth": quality["bandwidth"],
            "latency": 1,
            "pricing.cost": quality["price"],
        },
    }


def make_offers(ra_id, quality):
    result = {}
    for microservice in ("service-a", "service-b"):
        offer_id, offer = make_offer(ra_id, microservice, quality)
        result[microservice] = {offer_id: offer}
    return result


def make_agent(ra_id, offers, bus, job_id):
    agent = object.__new__(ResourceAgent)
    agent.ra_id = ra_id
    agent.logger = logging.getLogger(f"private-ranking-test.{ra_id}")
    agent.capacity = {"metadata": {"resource-provider": ra_id}}
    agent.capreg = FakeCapacityRegistry(offers)
    agent.peer = bus.endpoint(ra_id)
    agent.tkg_url = "http://tkg.test"
    agent.private_ranking_jobs = {}
    agent.private_ranking_public = {}
    agent.job_responses = {}
    agent.job_clients = {job_id: "test-client"}
    agent.job_offers = {}
    agent.job_tosca = {job_id: {"service_template": {}}}
    agent.job_states = {job_id: {"state": "Pending"}}
    agent.lead_resource = {}
    agent.tosca = {job_id: FakeTosca()}
    return agent


def test_complete_private_ranking_workflow(monkeypatch, tmp_path):
    """Run key issue through encrypted offers, selection, and provisioning handoff."""
    job_id = "private-workflow-job"
    bus = InProcessBus()
    hub = make_agent(
        "Hub-RA",
        make_offers("Hub-RA", {"energy": 80, "bandwidth": 100, "price": 80}),
        bus,
        job_id,
    )
    worker = make_agent(
        "Worker-RA",
        make_offers("Worker-RA", {"energy": 10, "bandwidth": 9000, "price": 5}),
        bus,
        job_id,
    )
    bus.agents = {"Hub-RA": hub, "Worker-RA": worker}

    # Keep the integration local while crossing the real FastAPI/Pydantic boundary.
    tkg_service.tkg = TrustedKeyGenerator()
    trust_store = FakeTrustStore()
    tkg_service.trust_store = trust_store
    client = TestClient(tkg_service.app)
    tkg_requests = []

    def post_to_tkg(url, json, timeout):
        path = url.removeprefix(hub.tkg_url)
        tkg_requests.append((path, deepcopy(json)))
        return client.post(path, json=json)

    monkeypatch.setattr(ra_base.requests, "post", post_to_tkg)
    monkeypatch.setattr(ra_base, "get_qos_priorities", lambda value: value)
    monkeypatch.setattr(ra_base.KBClient, "download_SAT_from_KB", lambda _: {
        "filename": "ask.yaml",
        "data": {"service_template": {}},
    })
    monkeypatch.setattr(ra_base.time, "sleep", lambda _: None)
    monkeypatch.setattr(random, "choice", lambda values: values[-1])
    monkeypatch.setenv("AUTO_APPROVE", "true")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "KB").mkdir()
    hub._get_independent_microservices = lambda _: ["service-a", "service-b"]

    # Hub obtains per-job material through the TKG HTTP API.
    public_context = hub._create_private_ranking_job(job_id)

    # Hub creates its local protected response; Worker follows the broadcast path.
    hub._process_job_requirements(
        job_id, "test-client", "ask.yaml", "Hub-RA", public_context
    )
    worker._handle_job_broadcast("Hub-RA", {
        "job_id": job_id,
        "client_id": "test-client",
        "hub_ra": "Hub-RA",
        "private_ranking": public_context,
    })

    resource_messages = [
        message for message in bus.messages if message[2] == "MSG_RESOURCE_RESPONSE"
    ]
    assert {message[0] for message in resource_messages} == {"Hub-RA", "Worker-RA"}
    for _, _, _, message in resource_messages:
        encoded = json.dumps(message["responses"])
        assert "characteristics" not in encoded
        assert "encrypted_qos" in encoded

    assert [path for path, _ in tkg_requests] == [
        "/v1/jobs",
        f"/v1/jobs/{job_id}/rank",
    ]
    rank_request = tkg_requests[-1][1]
    assert set(rank_request["offer_owners"].values()) == {"Hub-RA", "Worker-RA"}
    assert len(rank_request["combinations"]) == 4
    assert set(trust_store.lookups) == {"Hub-RA", "Worker-RA"}

    # Better Worker QoS and trusted reliability must select both Worker offers.
    selected = hub.job_offers[job_id]
    selected_owners = {
        next(iter(offers.values()))["ids"]["ra_id"] for offers in selected.values()
    }
    assert selected_owners == {"Worker-RA"}

    submit_messages = [
        message for message in bus.messages if message[2] == "MSG_SUBMIT_RESPONSE"
    ]
    assert submit_messages[-1][3]["result"] == "success"
    assert set(worker.capreg.accepted) == {
        "worker-ra-service-a", "worker-ra-service-b"
    }
    assert set(hub.capreg.rejected) == {"hub-ra-service-a", "hub-ra-service-b"}

    # Cloud creation is replaced by a controlled provisioner result. The real Hub
    # master-info handler must fan out remaining resources and mark the job Running.
    lead_requests = [
        message for message in bus.messages if message[2] == "MSG_CREATE_LEAD_RESOURCE"
    ]
    assert len(lead_requests) == 1
    assert lead_requests[0][1] == "Worker-RA"
    asyncio.run(hub._handle_master_info("Worker-RA", {
        "job_id": job_id,
        "timestamp": 1,
        "master_info": {
            "k3s_token": "test-token",
            "cluster_name": job_id,
            "master_ip": "192.0.2.10",
        },
    }))

    worker_create_messages = [
        message for message in bus.messages if message[2] == "MSG_CREATE_RESOURCE"
    ]
    assert len(worker_create_messages) == 1
    assert worker_create_messages[0][1] == "Worker-RA"
    assert worker_create_messages[0][3]["master_info"]["k3s_token"] == "test-token"
    assert hub.job_states[job_id]["state"] == "Running"
