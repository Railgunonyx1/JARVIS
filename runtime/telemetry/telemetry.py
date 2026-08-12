import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

try:
    import aiosqlite
except ImportError:  # pragma: no cover - optional dependency
    aiosqlite = None

class Telemetry:
    def __init__(self, db_path: str | None = None, batch_size: int = 100, flush_interval: float = 0.5):
        self.queue: asyncio.Queue[tuple[float, str, str]] = asyncio.Queue()
        self.db_path = Path(db_path) if db_path else Path(__file__).with_name('telemetry.db')
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._writer_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        await self._ensure_db()
        self._writer_task = asyncio.create_task(self._writer())

    async def _ensure_db(self) -> None:
        if aiosqlite is None:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    event_type TEXT,
                    data TEXT
                )
            ''')
            await db.commit()

    async def record(self, event_type: str, data: dict) -> None:
        await self.queue.put((time.time(), event_type, json.dumps(data)))

    async def _writer(self) -> None:
        if aiosqlite is None:
            return
        while not self._stop_event.is_set() or not self.queue.empty():
            batch: list[tuple[float, str, str]] = []
            try:
                # Wait for at least one event
                item = await asyncio.wait_for(self.queue.get(), timeout=self.flush_interval)
                batch.append(item)
            except TimeoutError:
                pass
            # Drain up to batch_size without waiting
            while len(batch) < self.batch_size:
                try:
                    batch.append(self.queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if batch:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.executemany(
                        'INSERT INTO telemetry (timestamp, event_type, data) VALUES (?, ?, ?)',
                        batch,
                    )
                    await db.commit()

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._writer_task:
            await self._writer_task

    @asynccontextmanager
    async def span(self, name: str):
        start = time.time()
        try:
            yield
        finally:
            duration_ms = (time.time() - start) * 1000
            await self.record('span', {'name': name, 'duration_ms': duration_ms})
