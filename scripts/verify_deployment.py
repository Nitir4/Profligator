#!/usr/bin/env python3
"""HTTP acceptance for a staging deployment with offline fixture connectors.

Creates a synthetic candidate, links/syncs a fixture profile, and revokes sharing.
Run only against an isolated/staging instance configured with fixture collectors.
"""

import argparse
import asyncio
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

import httpx


async def run(origin, output):
    key = uuid4().hex[:12]
    async with httpx.AsyncClient(base_url=origin, timeout=15) as owner, httpx.AsyncClient(base_url=origin, timeout=15) as guest:
        health = await guest.get("/health")
        assert health.status_code == 200 and health.json()["database"] == "ok"
        login = await guest.get("/login")
        assert login.status_code == 200 and '<div id="root">' in login.text
        assert (await guest.get("/api/v1/dashboard")).status_code == 401
        connectors = await guest.get("/api/v1/connectors")
        connectors.raise_for_status()
        descriptor = next(item for item in connectors.json() if item["platform"] == "leetcode")
        assert descriptor["mode"] == "fixture", "Use an isolated deployment configured with fixture collectors"
        registered = await owner.post("/api/v1/auth/register", json={"email":f"deploy-{key}@example.com",
            "handle":f"deploy_{key}","password":"DeploymentFixture2026!"})
        assert registered.status_code == 201
        assert (await owner.get("/api/v1/dashboard")).json()["total_problems_solved"] == 0
        profile = await owner.post("/api/v1/platform-profiles", json={"platform":"leetcode","handle_or_url":"fixture_deployment"})
        assert profile.status_code == 201
        sync = await owner.post("/api/v1/syncs", json={"platform_profile_id":profile.json()["id"]})
        assert sync.status_code == 202
        states = [sync.json()["status"]]
        deadline = monotonic() + 45
        while states[-1] not in {"succeeded","failed"} and monotonic() < deadline:
            await asyncio.sleep(.25)
            response = await owner.get(f"/api/v1/syncs/{sync.json()['id']}")
            response.raise_for_status()
            states.append(response.json()["status"])
        assert states[-1] == "succeeded", states
        assert (await owner.get("/api/v1/dashboard")).json()["total_problems_solved"] == 3
        sharing = await owner.put("/api/v1/sharing", json={"enabled":True})
        sharing.raise_for_status()
        token = sharing.json()["shareable_link"].rsplit("/",1)[1]
        shared = await guest.get(f"/api/v1/public-profiles/{token}")
        assert shared.status_code == 200
        assert "no-store" in shared.headers.get("cache-control", "")
        assert (await guest.get(f"/p/{token}")).status_code == 200
        assert (await owner.put("/api/v1/sharing", json={"enabled":False})).status_code == 200
        assert (await guest.get(f"/api/v1/public-profiles/{token}")).status_code == 404
        assert (await owner.post("/api/v1/auth/logout")).status_code == 204
        assert (await owner.get("/api/v1/dashboard")).status_code == 401
    report = {"passed":True,"origin":origin,"sync_states":list(dict.fromkeys(states)),
        "checks":["static web and SPA routes", "Nginx API proxy", "database health", "cookie registration and access guards",
                  "real worker synchronization and dashboard", "sharing/public view/cache policy/revocation", "logout"],
        "data":"synthetic staging account and LeetCode fixture; no live scraper, Google OAuth, TLS or Groq acceptance"}
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin",default="http://localhost:18080")
    parser.add_argument("--output",type=Path,default=Path("/tmp/profligator-deployment-check.json"))
    args = parser.parse_args()
    asyncio.run(run(args.origin,args.output))
