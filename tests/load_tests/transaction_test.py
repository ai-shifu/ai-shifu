"""
Simplified test script to verify transaction handling patterns in the optimized code.
This script tests the core transaction handling patterns without requiring the full application.
"""

import time
import threading
import random
import logging
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from redis import Redis

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

Base = declarative_base()


class TestRecord(Base):
    __tablename__ = "test_records"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(50), nullable=False)
    status = Column(Integer, default=0)
    data = Column(Text, nullable=True)


def create_db_session(db_uri):
    engine = create_engine(db_uri)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return scoped_session(session_factory)


def create_redis_client(host, port, db=0, password=None):
    return Redis(host=host, port=port, db=db, password=password)


def run_without_optimization(session, redis_client, user_id):
    lock_key = f"test:lock:{user_id}"
    lock = redis_client.lock(lock_key, timeout=5)

    try:
        if lock.acquire(blocking=False):
            try:
                record = TestRecord(user_id=user_id, status=0, data="Initial data")
                session.add(record)
                session.flush()

                time.sleep(0.5)

                record.status = 1
                record.data = "Updated data"

                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Error in transaction: {str(e)}")
                return False
            finally:
                lock.release()
        else:
            logger.warning(f"Failed to acquire lock for user {user_id}")
            return False
    except Exception as e:
        logger.error(f"Error in lock handling: {str(e)}")
        return False


def run_with_optimization(session, redis_client, user_id):
    lock_key = f"test:lock:{user_id}"
    lock = redis_client.lock(lock_key, timeout=30, blocking_timeout=3)

    session_committed = False

    try:
        if lock.acquire(blocking=True):
            try:
                with session.begin_nested():
                    record = TestRecord(user_id=user_id, status=0, data="Initial data")
                    session.add(record)
                    session.flush()
                    record_id = record.id
                    session.commit()

                lock.release()
                session_committed = True

                time.sleep(0.5)

                with session.begin_nested():
                    record = (
                        session.query(TestRecord)
                        .filter(TestRecord.id == record_id)
                        .first()
                    )
                    if record:
                        record.status = 1
                        record.data = "Updated data"
                    session.commit()

                session.commit()
                return True
            except Exception as e:
                session.rollback()
                logger.error(f"Error in transaction: {str(e)}")
                return False
            finally:
                if not session_committed and lock.owned():
                    lock.release()
        else:
            logger.warning(f"Failed to acquire lock for user {user_id}")
            return False
    except Exception as e:
        logger.error(f"Error in lock handling: {str(e)}")
        if "lock" in locals() and lock.owned():
            lock.release()
        return False


def run_concurrency_test(
    db_uri, redis_host, redis_port, redis_db=0, redis_password=None
):
    Session = create_db_session(db_uri)
    redis_client = create_redis_client(redis_host, redis_port, redis_db, redis_password)

    num_users = 20
    num_requests_per_user = 5

    start_time = time.time()
    success_count = 0
    failure_count = 0
    deadlock_count = 0

    def test_unoptimized(user_id):
        nonlocal success_count, failure_count, deadlock_count
        session = Session()
        try:
            for i in range(num_requests_per_user):
                result = run_without_optimization(
                    session, redis_client, f"{user_id}_{i}"
                )
                if result:
                    success_count += 1
                else:
                    failure_count += 1
                    if (
                        "deadlock"
                        in str(
                            session.execute("SHOW ENGINE INNODB STATUS").fetchall()
                        ).lower()
                    ):
                        deadlock_count += 1
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=num_users) as executor:
        executor.map(test_unoptimized, [f"user_{i}" for i in range(num_users)])

    unoptimized_duration = time.time() - start_time
    unoptimized_results = {
        "success_count": success_count,
        "failure_count": failure_count,
        "deadlock_count": deadlock_count,
        "duration": unoptimized_duration,
    }

    logger.info(f"Unoptimized test results: {unoptimized_results}")

    session = Session()
    session.query(TestRecord).delete()
    session.commit()
    session.close()

    start_time = time.time()
    success_count = 0
    failure_count = 0
    deadlock_count = 0

    def test_optimized(user_id):
        nonlocal success_count, failure_count, deadlock_count
        session = Session()
        try:
            for i in range(num_requests_per_user):
                result = run_with_optimization(session, redis_client, f"{user_id}_{i}")
                if result:
                    success_count += 1
                else:
                    failure_count += 1
                    if (
                        "deadlock"
                        in str(
                            session.execute("SHOW ENGINE INNODB STATUS").fetchall()
                        ).lower()
                    ):
                        deadlock_count += 1
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=num_users) as executor:
        executor.map(test_optimized, [f"user_{i}" for i in range(num_users)])

    optimized_duration = time.time() - start_time
    optimized_results = {
        "success_count": success_count,
        "failure_count": failure_count,
        "deadlock_count": deadlock_count,
        "duration": optimized_duration,
    }

    logger.info(f"Optimized test results: {optimized_results}")

    improvement = {
        "success_rate_improvement": (
            optimized_results["success_count"] / (num_users * num_requests_per_user)
        )
        - (unoptimized_results["success_count"] / (num_users * num_requests_per_user)),
        "deadlock_reduction": unoptimized_results["deadlock_count"]
        - optimized_results["deadlock_count"],
        "duration_improvement": unoptimized_duration - optimized_duration,
    }

    logger.info(f"Improvement: {improvement}")

    return {
        "unoptimized": unoptimized_results,
        "optimized": optimized_results,
        "improvement": improvement,
    }


if __name__ == "__main__":
    db_uri = "mysql://username:password@localhost:3306/test_db"
    redis_host = "localhost"
    redis_port = 6379

    results = run_concurrency_test(db_uri, redis_host, redis_port)
    print(f"Test results: {results}")
