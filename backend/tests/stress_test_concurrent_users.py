#!/usr/bin/env python3
"""
Stress test for concurrent users.

Phases:
1. SETUP: Create all users and chats (sequential, reliable)
2. STRESS TEST: Send all messages concurrently
3. CLEANUP: Delete chats after workflows finish
"""

import asyncio
import aiohttp
import argparse
import json
import random
import statistics
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class RequestMetrics:
    user_id: int
    session_id: int
    start_time: float
    end_time: float = 0.0
    first_token_time: float = 0.0
    success: bool = False
    error: Optional[str] = None

    @property
    def total_latency_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000 if self.end_time else 0

    @property
    def time_to_first_token_ms(self) -> float:
        return (self.first_token_time - self.start_time) * 1000 if self.first_token_time else 0


@dataclass
class LevelMetrics:
    level: int
    num_users: int
    total_messages: int
    setup_duration: float = 0.0
    test_duration: float = 0.0
    cleanup_duration: float = 0.0
    requests: List[RequestMetrics] = field(default_factory=list)

    @property
    def successful_requests(self):
        return [r for r in self.requests if r.success]

    @property
    def success_rate(self) -> float:
        return len(self.successful_requests) / len(self.requests) * 100 if self.requests else 0

    @property
    def throughput_rps(self) -> float:
        return len(self.requests) / self.test_duration if self.test_duration else 0

    def latency_stats(self) -> Dict[str, float]:
        latencies = sorted([r.total_latency_ms for r in self.successful_requests if r.total_latency_ms > 0])
        if not latencies:
            return {"min": 0, "max": 0, "mean": 0, "median": 0, "p95": 0, "p99": 0}
        return {
            "min": latencies[0],
            "max": latencies[-1],
            "mean": statistics.mean(latencies),
            "median": statistics.median(latencies),
            "p95": latencies[int(len(latencies) * 0.95)] if len(latencies) > 1 else latencies[0],
            "p99": latencies[int(len(latencies) * 0.99)] if len(latencies) > 1 else latencies[0],
        }

    def ttft_stats(self) -> Dict[str, float]:
        ttfts = sorted([r.time_to_first_token_ms for r in self.successful_requests if r.time_to_first_token_ms > 0])
        if not ttfts:
            return {"min": 0, "max": 0, "mean": 0, "median": 0, "p95": 0, "p99": 0}
        return {
            "min": ttfts[0],
            "max": ttfts[-1],
            "mean": statistics.mean(ttfts),
            "median": statistics.median(ttfts),
            "p95": ttfts[int(len(ttfts) * 0.95)] if len(ttfts) > 1 else ttfts[0],
            "p99": ttfts[int(len(ttfts) * 0.99)] if len(ttfts) > 1 else ttfts[0],
        }


class StressTestRunner:
    def __init__(self, base_url: str, openai_key: str, lf_public: str, lf_secret: str):
        self.base_url = base_url.rstrip("/")
        self.openai_key = openai_key
        self.lf_public = lf_public
        self.lf_secret = lf_secret
        self.session: Optional[aiohttp.ClientSession] = None
        self.users: Dict[int, Dict] = {}  # {user_num: {"token": str, "session_id": int}}

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def setup_user(self, user_num: int, user_id: str, retries: int = 3) -> bool:
        """Setup single user with retries. Uses random user_id for uniqueness."""
        email = f"bench_{user_id}@test.local"
        password = "bench123!"

        for attempt in range(retries):
            try:
                # Try signup first
                async with self.session.post(
                    f"{self.base_url}/api/auth/signup/",
                    json={"email": email, "password": password, "first_name": "Bench", "last_name": user_id},
                ) as resp:
                    if resp.status == 201:
                        token = (await resp.json())["access"]
                    elif resp.status == 400:
                        # User exists, login
                        async with self.session.post(
                            f"{self.base_url}/api/auth/login/",
                            json={"email": email, "password": password},
                        ) as login_resp:
                            if login_resp.status != 200:
                                continue
                            token = (await login_resp.json())["access"]
                    else:
                        continue

                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

                # Set API keys
                async with self.session.put(
                    f"{self.base_url}/api/users/me/api-keys/update/",
                    json={"openai_api_key": self.openai_key, "langfuse_public_key": self.lf_public, "langfuse_secret_key": self.lf_secret},
                    headers=headers,
                ) as resp:
                    if resp.status != 200:
                        continue

                # Create chat
                async with self.session.post(
                    f"{self.base_url}/api/chats/",
                    json={"title": f"Bench {user_id}"},
                    headers=headers,
                ) as resp:
                    if resp.status == 201:
                        session_id = (await resp.json())["id"]
                        self.users[user_num] = {"token": token, "session_id": session_id}
                        return True

            except Exception as e:
                if attempt == retries - 1:
                    print(f"  User {user_num} setup failed: {e}")

            await asyncio.sleep(0.5)

        return False

    async def send_message(self, user_num: int) -> RequestMetrics:
        """Send single message and consume stream."""
        user = self.users.get(user_num)
        metrics = RequestMetrics(user_num, user["session_id"] if user else 0, time.time())

        if not user:
            metrics.error = "No user"
            metrics.end_time = time.time()
            return metrics

        try:
            headers = {"Authorization": f"Bearer {user['token']}", "Content-Type": "application/json"}
            payload = {
                "chat_session_id": user["session_id"],
                "message": "hi",
                "model": "gpt-3.5-turbo",
                "max_tokens": 5,
                "flow": "main",
                "idempotency_key": str(uuid.uuid4()),
            }

            async with self.session.post(
                f"{self.base_url}/api/agent/stream/",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status != 200:
                    metrics.error = f"HTTP {resp.status}"
                    metrics.end_time = time.time()
                    return metrics

                first_token = False
                async for line in resp.content:
                    line = line.decode().strip()
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                        etype = event.get("type", "")
                        if etype == "token" and not first_token:
                            metrics.first_token_time = time.time()
                            first_token = True
                        elif etype in ("done", "final"):
                            break
                        elif etype == "error":
                            metrics.error = event.get("data", {}).get("error", "Unknown")
                            break
                    except:
                        continue

                metrics.end_time = time.time()
                metrics.success = metrics.error is None

        except asyncio.TimeoutError:
            metrics.error = "Timeout"
            metrics.end_time = time.time()
        except Exception as e:
            metrics.error = str(e)[:40]
            metrics.end_time = time.time()

        return metrics

    async def delete_chat(self, user_num: int):
        user = self.users.get(user_num)
        if not user:
            return
        try:
            headers = {"Authorization": f"Bearer {user['token']}"}
            await self.session.delete(f"{self.base_url}/api/chats/{user['session_id']}/", headers=headers)
        except:
            pass


async def run_level(level: int, num_users: int, base_url: str,
                    openai_key: str, lf_public: str, lf_secret: str) -> LevelMetrics:

    print(f"\n{'='*60}")
    print(f"LEVEL {level}: {num_users} users, each sends 1 message")
    print(f"TRUE CONCURRENT: All {num_users} messages fired at SAME TIME!")
    print(f"{'='*60}")

    metrics = LevelMetrics(level=level, num_users=num_users, total_messages=num_users)

    async with StressTestRunner(base_url, openai_key, lf_public, lf_secret) as runner:

        # Generate random 6-digit IDs for each user
        user_ids = [str(random.randint(100000, 999999)) for _ in range(num_users)]

        # ===== PHASE 1: SETUP (all users created before any messages) =====
        print(f"\n[1/3 SETUP] Creating {num_users} users with chats...")
        setup_start = time.time()

        # Setup uses semaphore to avoid overwhelming DB during user creation
        setup_sem = asyncio.Semaphore(50)
        async def setup_one(i, user_id):
            async with setup_sem:
                return await runner.setup_user(i, user_id)

        results = await asyncio.gather(*[setup_one(i, uid) for i, uid in enumerate(user_ids)])
        setup_ok = sum(results)
        metrics.setup_duration = time.time() - setup_start
        print(f"[1/3 SETUP] Done: {setup_ok}/{num_users} users in {metrics.setup_duration:.1f}s")

        if setup_ok == 0:
            print("[ERROR] No users created!")
            return metrics

        # ===== PHASE 2: STRESS TEST (ALL messages at SAME TIME) =====
        print(f"\n[2/3 STRESS TEST] Firing {num_users} messages SIMULTANEOUSLY...")
        test_start = time.time()

        # Each user sends exactly 1 message - all at once
        user_nums = [i for i in range(num_users) if i in runner.users]

        # Fire ALL at once - NO SEMAPHORE, NO THROTTLE
        pending = [runner.send_message(u) for u in user_nums]
        done_count = 0
        total = len(pending)

        for coro in asyncio.as_completed(pending):
            result = await coro
            metrics.requests.append(result)
            done_count += 1
            # Print every 10%
            if done_count % max(1, total // 10) == 0:
                ok = sum(1 for r in metrics.requests if r.success)
                fail = done_count - ok
                print(f"  {done_count}/{total} done ({ok} ok, {fail} fail) [{time.time()-test_start:.1f}s]")

        metrics.test_duration = time.time() - test_start
        print(f"[2/3 STRESS TEST] Done in {metrics.test_duration:.1f}s")

        # ===== PHASE 3: CLEANUP =====
        print(f"\n[3/3 CLEANUP] Waiting 3s then deleting chats...")
        await asyncio.sleep(3)
        cleanup_start = time.time()

        await asyncio.gather(*[runner.delete_chat(i) for i in runner.users.keys()])
        metrics.cleanup_duration = time.time() - cleanup_start
        print(f"[3/3 CLEANUP] Done in {metrics.cleanup_duration:.1f}s")

    return metrics


def print_summary(m: LevelMetrics):
    lat = m.latency_stats()
    ttft = m.ttft_stats()
    print(f"\n{'-'*60}")
    print(f"LEVEL {m.level} RESULTS")
    print(f"{'-'*60}")
    print(f"Users: {m.num_users} | Messages: {m.total_messages}")
    print(f"Setup: {m.setup_duration:.1f}s | Test: {m.test_duration:.1f}s | Cleanup: {m.cleanup_duration:.1f}s")
    print(f"\nSuccess: {len(m.successful_requests)}/{len(m.requests)} ({m.success_rate:.1f}%)")
    print(f"Throughput: {m.throughput_rps:.1f} req/s")
    print(f"\nLatency (ms): min={lat['min']:.0f} median={lat['median']:.0f} p95={lat['p95']:.0f} max={lat['max']:.0f}")
    print(f"TTFT (ms):    min={ttft['min']:.0f} median={ttft['median']:.0f} p95={ttft['p95']:.0f} max={ttft['max']:.0f}")

    failed = [r for r in m.requests if not r.success]
    if failed:
        errors = {}
        for r in failed:
            errors[r.error or "Unknown"] = errors.get(r.error, 0) + 1
        print(f"\nErrors:")
        for e, c in sorted(errors.items(), key=lambda x: -x[1])[:5]:
            print(f"  {c}x {e}")


def generate_report(all_metrics: List[LevelMetrics], base_url: str) -> str:
    report = f"""# Stress Test Results

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Target:** {base_url}

## Summary

| Level | Users | Messages | Success | Throughput | Median Latency | p95 |
|-------|-------|----------|---------|------------|----------------|-----|
"""
    for m in all_metrics:
        lat = m.latency_stats()
        report += f"| {m.level} | {m.num_users} | {m.total_messages} | {m.success_rate:.0f}% | {m.throughput_rps:.1f}/s | {lat['median']:.0f}ms | {lat['p95']:.0f}ms |\n"

    for m in all_metrics:
        lat = m.latency_stats()
        ttft = m.ttft_stats()
        report += f"""
## Level {m.level}

- Setup: {m.setup_duration:.1f}s | Test: {m.test_duration:.1f}s
- Success: {m.success_rate:.1f}% | Throughput: {m.throughput_rps:.1f} req/s
- Latency: median={lat['median']:.0f}ms, p95={lat['p95']:.0f}ms
- TTFT: median={ttft['median']:.0f}ms, p95={ttft['p95']:.0f}ms
"""
    return report


# Each level = N users, each sends 1 message simultaneously
TEST_LEVELS = {1: 10, 2: 20, 3: 50, 4: 100, 5: 200}


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--level", type=int, choices=[1, 2, 3, 4, 5])
    p.add_argument("--api-key", required=True)
    p.add_argument("--langfuse-public", required=True)
    p.add_argument("--langfuse-secret", required=True)
    p.add_argument("--output", default="/app/docs/STRESS_TEST_RESULTS.md")
    args = p.parse_args()

    print("="*60)
    print("CONCURRENT USERS STRESS TEST (TRUE CONCURRENCY)")
    print("Levels: 10 / 20 / 50 / 100 / 200 simultaneous users")
    print("="*60)

    levels = [args.level] if args.level else [1, 2, 3, 4, 5]
    all_metrics = []

    for lvl in levels:
        num_users = TEST_LEVELS[lvl]
        m = await run_level(lvl, num_users, args.base_url,
                           args.api_key, args.langfuse_public, args.langfuse_secret)
        all_metrics.append(m)
        print_summary(m)

        # Stop if success rate drops below 95%
        if m.success_rate < 95:
            print(f"\n[STOP] Success rate {m.success_rate:.1f}% < 95%, stopping tests.")
            break

    # Save report
    try:
        import os
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w") as f:
            f.write(generate_report(all_metrics, args.base_url))
        print(f"\nReport: {args.output}")
    except Exception as e:
        print(f"Failed to save: {e}")


if __name__ == "__main__":
    asyncio.run(main())
