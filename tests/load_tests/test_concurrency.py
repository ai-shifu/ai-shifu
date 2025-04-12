import asyncio
import aiohttp
import time
import json
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:5000"  # 根据实际环境调整
CONCURRENT_USERS = 10  # 并发用户数
TEST_DURATION = 30  # 测试持续时间（秒）
USER_ID = "test_user_id"  # 测试用户ID
COURSE_ID = "test_course_id"  # 测试课程ID
LESSON_ID = "test_lesson_id"  # 测试课程ID


class Stats:
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.deadlocks = 0
        self.timeouts = 0
        self.response_times = []
        self.start_time = None
        self.end_time = None

    def add_response_time(self, time_ms):
        self.response_times.append(time_ms)

    def start(self):
        self.start_time = datetime.now()

    def stop(self):
        self.end_time = datetime.now()

    def get_summary(self):
        if not self.response_times:
            avg_response_time = 0
        else:
            avg_response_time = sum(self.response_times) / len(self.response_times)

        duration = 0
        if self.start_time and self.end_time:
            duration = (self.end_time - self.start_time).total_seconds()

        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "deadlocks": self.deadlocks,
            "timeouts": self.timeouts,
            "avg_response_time_ms": avg_response_time,
            "requests_per_second": (
                self.total_requests / duration if duration > 0 else 0
            ),
            "duration_seconds": duration,
        }


async def test_run_script(session, stats):
    url = f"{BASE_URL}/api/study/run"
    data = {
        "user_id": USER_ID,
        "course_id": COURSE_ID,
        "lesson_id": LESSON_ID,
        "input_type": "START",
    }

    start_time = time.time()
    stats.total_requests += 1

    try:
        async with session.post(url, json=data, timeout=10) as response:
            if response.status == 200:
                stats.successful_requests += 1
                async for _ in response.content.iter_any():
                    break
            else:
                stats.failed_requests += 1
                response_text = await response.text()
                if "deadlock" in response_text.lower():
                    stats.deadlocks += 1
                    logger.error(f"Deadlock detected: {response_text}")
                logger.error(f"Error response: {response.status} - {response_text}")
    except asyncio.TimeoutError:
        stats.failed_requests += 1
        stats.timeouts += 1
        logger.error("Request timed out")
    except Exception as e:
        stats.failed_requests += 1
        logger.error(f"Request failed: {str(e)}")

    end_time = time.time()
    stats.add_response_time((end_time - start_time) * 1000)  # 转换为毫秒


async def test_reset_study_progress(session, stats):
    url = f"{BASE_URL}/api/study/reset-study-progress"
    data = {"user_id": USER_ID, "lesson_id": LESSON_ID}

    start_time = time.time()
    stats.total_requests += 1

    try:
        async with session.post(url, json=data, timeout=5) as response:
            response_text = await response.text()
            if response.status == 200:
                stats.successful_requests += 1
            else:
                stats.failed_requests += 1
                if "deadlock" in response_text.lower():
                    stats.deadlocks += 1
                    logger.error(f"Deadlock detected: {response_text}")
                logger.error(f"Error response: {response.status} - {response_text}")
    except asyncio.TimeoutError:
        stats.failed_requests += 1
        stats.timeouts += 1
        logger.error("Request timed out")
    except Exception as e:
        stats.failed_requests += 1
        logger.error(f"Request failed: {str(e)}")

    end_time = time.time()
    stats.add_response_time((end_time - start_time) * 1000)  # 转换为毫秒


async def user_behavior(session, user_id, run_stats, reset_stats):
    end_time = time.time() + TEST_DURATION

    while time.time() < end_time:
        if random.random() < 0.8:
            await test_run_script(session, run_stats)
        else:
            await test_reset_study_progress(session, reset_stats)

        await asyncio.sleep(random.uniform(0.1, 0.5))


async def run_load_test():
    run_stats = Stats()
    reset_stats = Stats()

    run_stats.start()
    reset_stats.start()

    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(CONCURRENT_USERS):
            task = asyncio.create_task(
                user_behavior(session, f"user_{i}", run_stats, reset_stats)
            )
            tasks.append(task)

        await asyncio.gather(*tasks)

    run_stats.stop()
    reset_stats.stop()

    logger.info("Load test completed")
    logger.info(
        f"Run Script API Stats: {json.dumps(run_stats.get_summary(), indent=2)}"
    )
    logger.info(
        f"Reset Study Progress API Stats: {json.dumps(reset_stats.get_summary(), indent=2)}"
    )

    if run_stats.deadlocks > 0 or reset_stats.deadlocks > 0:
        logger.error(
            f"Detected {run_stats.deadlocks + reset_stats.deadlocks} deadlocks during testing"
        )

    if run_stats.timeouts > 0 or reset_stats.timeouts > 0:
        logger.error(
            f"Detected {run_stats.timeouts + reset_stats.timeouts} timeouts during testing"
        )

    return run_stats, reset_stats


if __name__ == "__main__":
    import random

    logger.info(
        f"Starting load test with {CONCURRENT_USERS} concurrent users for {TEST_DURATION} seconds"
    )
    asyncio.run(run_load_test())
