#!/usr/bin/env python
with open('memory/api.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Find the retrieve_items method and enhance it with prior usefulness
old_retrieve = """    def retrieve_items(
        self,
        query: str,
        project: str = "",
        top_k: int = 3,
        min_score: float = 0.15,
    ) -> list[MemoryItem]:
        """Merged candidates from every source, hybrid-ranked, top_k returned."""
        candidates: list[MemoryItem] = []

        # Hot-tier fast path — point lookups by exact key are near-free.
        if self._controller._tiers is not None:
            hot = self._controller._tiers.retrieve(query)
            if hot is not None:
                candidates.append(MemoryItem(
                    id=f"tier:{query}", content=str(hot),
                    type="hot", importance=0.8,
                    last_accessed=time.time(), access_count=1,
                ))
                candidates[-1]._signals = {"semantic": 0.5, "lexical": 0.5}

        if self._controller._vector is not None:
            for hit in self._controller._vector.search_similar(query, top_k=max(top_k * 3, 3), min_score=min_score):
                meta = self._controller._metadata.get(str(hit["id"])) if self._controller._metadata else None
                item = MemoryItem(
                    id=f"v:{hit['id']}",
                    content=hit["text"],
                    type=hit["category"],
                    importance=meta["importance"] if meta else 0.5,
                    last_accessed=meta["last_used"] if meta else hit.get("created_at", time.time()),
                    access_count=meta["access_count"] if meta else 0,
                    project=(meta or {}).get("project", ""),
                    created_at=hit.get("created_at", time.time()),
                )
                item._signals = {"semantic": hit["score"], "lexical": 0.0}
                candidates.append(item)

        if self._controller._kv is not None:
            for row in self._controller._kv.search_lexical(query, limit=max(top_k * 3, 3)):
                key = row["key"]
                meta = self._controller._metadata.get(key) if self._controller._metadata else None
                from core.context.selector import score as _lexical_score
                lexical = _lexical_score(f"{key.replace('_', ' ')} {row['value']}", query)
                item = MemoryItem(
                    id=f"kv:{key}", content=row["value"],
                    type=row["category"],
                    importance=meta["importance"] if meta else 0.5,
                    last_accessed=meta["last_used"] if meta else time.time(),
                    access_count=meta["access_count"] if meta else 0,
                    project=(meta or {}).get("project", ""),
                    created_at=(meta or {}).get("created", time.time()),
                )
                item._signals = {"semantic": 0.0, "lexical": lexical}
                candidates.append(item)

        if self._controller._decisions is not None:
            for row in self._controller._decisions.recall(project=project, query=query, limit=max(top_k * 3, 3)):
                content = f"{row.get('goal')} — {row.get('decision')} ({row.get('rationale')})"
                item = MemoryItem(
                    id=f"d:{row['id']}",
                    content=content,
                    type=DECISION,
                    project=row.get("project", ""),
                    importance=0.7,
                    created_at=row.get("created_at", time.time()),
                    last_accessed=row.get("created_at", time.time()),
                    metadata={k: row.get(k) for k in ("goal", "decision", "rationale", "outcome")},
                )
                item._signals = {"semantic": 0.0, "lexical": _lexical_score(content, query)}
                candidates.append(item)

        if not candidates:
            return []"""

new_retrieve = """    def retrieve_items(
        self,
        query: str,
        project: str = "",
        top_k: int = 3,
        min_score: float = 0.15,
    ) -> list[MemoryItem]:
        """Merged candidates from every source, hybrid-ranked, top_k returned."""
        candidates: list[MemoryItem] = []

        # Hot-tier fast path — point lookups by exact key are near-free.
        if self._controller._tiers is not None:
            hot = self._controller._tiers.retrieve(query)
            if hot is not None:
                candidates.append(MemoryItem(
                    id=f"tier:{query}", content=str(hot),
                    type="hot", importance=0.8,
                    last_accessed=time.time(), access_count=1,
                ))
                candidates[-1]._signals = {"semantic": 0.5, "lexical": 0.5}

        if self._controller._vector is not None:
            for hit in self._controller._vector.search_similar(query, top_k=max(top_k * 3, 3), min_score=min_score):
                meta = self._controller._metadata.get(str(hit["id"])) if self._controller._metadata else None
                item = MemoryItem(
                    id=f"v:{hit['id']}",
                    content=hit["text"],
                    type=hit["category"],
                    importance=meta["importance"] if meta else 0.5,
                    last_accessed=meta["last_used"] if meta else hit.get("created_at", time.time()),
                    access_count=meta["access_count"] if meta else 0,
                    project=(meta or {}).get("project", ""),
                    created_at=hit.get("created_at", time.time()),
                )
                item._signals = {"semantic": hit["score"], "lexical": 0.0}
                candidates.append(item)

        if self._controller._kv is not None:
            for row in self._controller._kv.search_lexical(query, limit=max(top_k * 3, 3)):
                key = row["key"]
                meta = self._controller._metadata.get(key) if self._controller._metadata else None
                from core.context.selector import score as _lexical_score
                lexical = _lexical_score(f"{key.replace('_', ' ')} {row['value']}", query)
                item = MemoryItem(
                    id=f"kv:{key}", content=row["value"],
                    type=row["category"],
                    importance=meta["importance"] if meta else 0.5,
                    last_accessed=meta["last_used"] if meta else time.time(),
                    access_count=meta["access_count"] if meta else 0,
                    project=(meta or {}).get("project", ""),
                    created_at=(meta or {}).get("created", time.time()),
                )
                item._signals = {"semantic": 0.0, "lexical": lexical}
                candidates.append(item)

        if self._controller._decisions is not None:
            for row in self._controller._decisions.recall(project=project, query=query, limit=max(top_k * 3, 3)):
                content = f"{row.get('goal')} — {row.get('decision')} ({row.get('rationale')})"
                item = MemoryItem(
                    id=f"d:{row['id']}",
                    content=content,
                    type=DECISION,
                    project=row.get("project", ""),
                    importance=0.7,
                    created_at=row.get("created_at", time.time()),
                    last_accessed=row.get("created_at", time.time()),
                    metadata={k: row.get(k) for k in ("goal", "decision", "rationale", "outcome")},
                )
                item._signals = {"semantic": 0.0, "lexical": _lexical_score(content, query)}
                candidates.append(item)

        # --- Prior usefulness enhancement ---
        # Increment access_count for all returned candidates (prior-usefulness signal)
        # and update metadata so frequently-accessed memories rank higher next time.
        now = time.time()
        if self._controller._metadata is not None:
            for item in candidates:
                logical = str(item.id)
                if logical.startswith("kv:"):
                    self._controller._metadata.touch(logical[3:])
                    # Increment access count
                    entry = self._controller._metadata.get(logical[3:])
                    if entry:
                        entry["access_count"] = entry.get("access_count", 0) + 1
                        self._controller._metadata.set_importance(logical[3:], entry.get("importance", 0.5))
                elif logical.startswith("v:"):
                    self._controller._metadata.touch(logical)
                    entry = self._controller._metadata.get(logical)
                    if entry:
                        entry["access_count"] = entry.get("access_count", 0) + 1
                        self._controller._metadata.set_importance(logical, entry.get("importance", 0.5))

        if not candidates:
            return []"""

if old_retrieve in content:
    new_content = content.replace(old_retrieve, new_retrieve)
    with open('memory/api.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Memory retrieval enhanced with prior usefulness')
else:
    print('Old retrieve method not found')
    idx = content.find('def retrieve_items')
    if idx >= 0:
        print('Found at index', idx)
        print(content[idx:idx+200])