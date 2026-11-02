from datetime import UTC, datetime

from newsloom_mcp.response_cache import Entry, ResponseCache


def test_exact_non_sliding_expiry_and_restart() -> None:
    now = [0.0]
    cache = ResponseCache(lambda: now[0])
    entry = Entry(b'{"items":[]}', datetime.now(UTC), 0, "page")
    assert cache.put("a" * 64, entry)
    now[0] = 59.999
    assert cache.get("a" * 64) == entry
    now[0] = 60
    assert cache.get("a" * 64) is None and cache.bytes == 0
    assert not cache.put("b" * 64, entry)
    assert ResponseCache(lambda: now[0]).get("a" * 64) is None


def test_byte_entry_and_lru_bounds_oversized_bypass() -> None:
    cache = ResponseCache(lambda: 0)

    def entry(size: int) -> Entry:
        return Entry(b"x" * size, datetime.now(UTC), 0, "page")

    assert not cache.put("a" * 64, entry(512 * 1024 + 1))
    for i in range(17):
        assert cache.put(f"{i:064x}", entry(512 * 1024))
    assert len(cache.entries) == 16 and cache.bytes == 8 * 1024 * 1024
    assert cache.get(f"{0:064x}") is None
    assert cache.get(f"{1:064x}") is not None
    assert cache.put("f" * 64, entry(512 * 1024))
    assert cache.get(f"{2:064x}") is None
    small = ResponseCache(lambda: 0)
    for i in range(129):
        assert small.put(f"{i:064x}", entry(1))
    assert len(small.entries) == 128 and small.bytes == 128
    assert small.get(f"{0:064x}") is None
