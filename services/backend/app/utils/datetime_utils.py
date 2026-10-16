"""
Datetime Utilities

Phase 27.1: datetime 비교 에러 수정
- timezone-aware와 timezone-naive datetime 비교 문제 해결
"""
from datetime import datetime, timezone
from typing import Optional


def get_safe_datetime_for_sort(dt: Optional[datetime]) -> datetime:
    """
    정렬에 안전한 datetime 값 반환

    timezone-aware datetime과 None 값을 안전하게 비교할 수 있도록
    timezone-aware 기본값을 반환합니다.

    Args:
        dt: datetime 값 또는 None

    Returns:
        timezone-aware datetime (None인 경우 datetime.min + UTC)
    """
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return dt