"""
백엔드 DB 연결 재시도 테스트

Docker 가 재시작 정책으로 컨테이너를 되살릴 때는
depends_on(healthy) 이 지켜지지 않아,
백엔드가 Postgres 보다 먼저 떠서
"the database system is starting up" 으로 한 번 실패하면
메모리 대체 모드로 굳었다(로그·세션·히스토리 전부 동작 안 함). 준비될 때까지 재시도한다.
"""

import pytest


class FlakyDb:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def connect(self) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise ConnectionError("the database system is starting up")


async def _no_sleep(_: float) -> None:
    return None


@pytest.mark.asyncio
async def test_should_connect_after_database_finishes_starting() -> None:
    from services.backend.app.database.connection import connect_with_retry

    db = FlakyDb(failures=3)

    await connect_with_retry(db, attempts=10, delay=0, sleep=_no_sleep)

    assert db.calls == 4


@pytest.mark.asyncio
async def test_should_raise_when_database_never_comes_up() -> None:
    from services.backend.app.database.connection import connect_with_retry

    db = FlakyDb(failures=100)

    with pytest.raises(ConnectionError):
        await connect_with_retry(db, attempts=5, delay=0, sleep=_no_sleep)

    assert db.calls == 5
