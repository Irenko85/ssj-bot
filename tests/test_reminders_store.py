from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils import reminders_store
from utils.reminders_store import RemindersStore


@pytest.mark.asyncio
async def test_create_inserts_row_and_returns_inserted_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    query = MagicMock()
    query.execute = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                {
                    "id": "rem-1",
                    "message": "ver la peli",
                    "target_ids": ["111", "222"],
                    "fire_at": "2026-05-26T01:00:00+00:00",
                    "channel_id": "333",
                    "created_by": "444",
                    "done": False,
                }
            ]
        )
    )
    table = MagicMock()
    table.insert.return_value = query
    client.table.return_value = table

    async def fake_create_client(url: str, key: str):
        assert url == "https://example.supabase.co"
        assert key == "test-key"
        return client

    monkeypatch.setattr(
        reminders_store, "_create_async_supabase_client", fake_create_client
    )

    store = RemindersStore("https://example.supabase.co", "test-key")
    fire_at = datetime(2026, 5, 26, 1, 0, tzinfo=timezone.utc)

    result = await store.create(
        message="ver la peli",
        target_ids=["111", "222"],
        fire_at=fire_at,
        channel_id="333",
        created_by="444",
    )

    client.table.assert_called_once_with("reminders")
    table.insert.assert_called_once_with(
        {
            "message": "ver la peli",
            "target_ids": ["111", "222"],
            "fire_at": "2026-05-26T01:00:00+00:00",
            "channel_id": "333",
            "created_by": "444",
            "done": False,
        }
    )
    assert result["id"] == "rem-1"


@pytest.mark.asyncio
async def test_get_pending_returns_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    query = MagicMock()
    query.eq.return_value = query
    query.gt.return_value = query
    query.order.return_value = query
    query.execute = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                {
                    "id": "rem-1",
                    "message": "ver la peli",
                    "target_ids": ["111"],
                    "fire_at": "2026-05-26T01:00:00+00:00",
                    "channel_id": "333",
                    "created_by": "444",
                    "done": False,
                }
            ]
        )
    )
    table = MagicMock()
    table.select.return_value = query
    client.table.return_value = table

    async def fake_create_client(url: str, key: str):
        return client

    monkeypatch.setattr(
        reminders_store, "_create_async_supabase_client", fake_create_client
    )

    store = RemindersStore("https://example.supabase.co", "test-key")

    result = await store.get_pending()

    client.table.assert_called_once_with("reminders")
    table.select.assert_called_once_with("*")
    query.eq.assert_called_once_with("done", False)
    assert query.gt.call_args.args[0] == "fire_at"
    query.order.assert_called_once_with("fire_at")
    assert result[0]["id"] == "rem-1"


@pytest.mark.asyncio
async def test_mark_done_updates_row(monkeypatch: pytest.MonkeyPatch) -> None:
    client = MagicMock()
    query = MagicMock()
    query.eq.return_value = query
    query.execute = AsyncMock(return_value=SimpleNamespace(data=[]))
    table = MagicMock()
    table.update.return_value = query
    client.table.return_value = table

    async def fake_create_client(url: str, key: str):
        return client

    monkeypatch.setattr(
        reminders_store, "_create_async_supabase_client", fake_create_client
    )

    store = RemindersStore("https://example.supabase.co", "test-key")

    await store.mark_done("rem-1")

    client.table.assert_called_once_with("reminders")
    table.update.assert_called_once_with({"done": True})
    query.eq.assert_called_once_with("id", "rem-1")


@pytest.mark.asyncio
async def test_create_rejects_naive_datetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    query = MagicMock()
    query.execute = AsyncMock(return_value=SimpleNamespace(data=[{"id": "x"}]))

    table = MagicMock()
    table.insert.return_value = query
    client.table.return_value = table

    async def fake_create_client(url: str, key: str):
        return client

    monkeypatch.setattr(
        reminders_store, "_create_async_supabase_client", fake_create_client
    )

    store = RemindersStore("https://example.supabase.co", "test-key")
    naive_fire_at = datetime(2026, 5, 26, 1, 0)  # sin tzinfo

    with pytest.raises(ValueError, match=r"fire_at debe ser timezone-aware"):
        await store.create(
            message="test",
            target_ids=["111"],
            fire_at=naive_fire_at,
            channel_id="333",
            created_by="444",
        )
