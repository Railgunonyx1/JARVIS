"""Tests for the local ONNX cross-encoder rerank lane.

Hermetic: a fake ``onnxruntime`` module stands in for the real runtime, so
these tests exercise tokenization, padding, attention masks, token types and
score mapping without downloading or loading a model.
"""

from __future__ import annotations

import sys
import types

import pytest

VOCAB_LINES = [
    "[PAD]", "[UNK]", "[CLS]", "[SEP]",
    "the", "user", "name", "is", "python", "project", "likes", "memory",
]
ID_NAME = 6
ID_MEMORY = 11


def _make_fake_ort():
    """A stand-in onnxruntime whose logits reward rows containing ``name``."""
    import numpy as np

    class SessionOptions:
        def __init__(self):
            self.intra_op_num_threads = 0
            self.inter_op_num_threads = 0
            self.execution_mode = None
            self.graph_optimization_level = None

    class ExecutionMode:
        ORT_SEQUENTIAL = "seq"

    class GraphOptimizationLevel:
        ORT_ENABLE_ALL = "all"

    def inference_session(path, sess_options=None, providers=None):
        fake.last_path = path
        fake.last_providers = providers

        class _Input:
            def __init__(self, name):
                self.name = name

        class _Session:
            def get_inputs(self):
                return [_Input("input_ids"), _Input("attention_mask"), _Input("token_type_ids")]

            def run(self, _outputs, feed):
                fake.last_feed = feed
                ids = feed["input_ids"]
                scores = np.array(
                    [float((row == ID_NAME).sum()) * 2.0 + (row == ID_MEMORY).sum() * 0.1
                     for row in ids],
                    dtype=np.float32,
                )
                return [scores.reshape(-1, 1)]

        return _Session()

    fake = types.ModuleType("onnxruntime")
    fake.SessionOptions = SessionOptions
    fake.ExecutionMode = ExecutionMode
    fake.GraphOptimizationLevel = GraphOptimizationLevel
    fake.InferenceSession = inference_session
    fake.CPUExecutionProvider = "CPUExecutionProvider"
    return fake


@pytest.fixture
def lane(tmp_path, monkeypatch):
    """A cross-encoder lane backed by a fake runtime and a tiny real vocab."""
    from memory import cross_encoder

    (tmp_path / "vocab.txt").write_text("\n".join(VOCAB_LINES) + "\n", encoding="utf-8")
    (tmp_path / "model.onnx").write_bytes(b"not-a-real-onnx-graph")

    monkeypatch.setitem(sys.modules, "onnxruntime", _make_fake_ort())
    monkeypatch.setenv("JARVIS_RERANKER_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_RERANKER", "auto")

    cross_encoder._state.update({"tried": False, "ok": False, "session": None, "vocab": None})
    cross_encoder._cache.clear()
    yield cross_encoder
    cross_encoder._state.update({"tried": False, "ok": False, "session": None, "vocab": None})
    cross_encoder._cache.clear()


class TestGracefulDegradation:
    """The lane must never raise or block retrieval when it cannot run."""

    def test_missing_model_dir_disables_lane(self, monkeypatch, tmp_path):
        from memory import cross_encoder

        monkeypatch.delenv("JARVIS_RERANKER", raising=False)
        monkeypatch.setenv("JARVIS_RERANKER_DIR", str(tmp_path / "absent"))
        cross_encoder._state.update({"tried": False, "ok": False, "session": None, "vocab": None})
        assert cross_encoder.available() is False

    def test_score_returns_none_when_unavailable(self, monkeypatch, tmp_path):
        from memory import cross_encoder

        monkeypatch.setenv("JARVIS_RERANKER", "off")
        monkeypatch.setenv("JARVIS_RERANKER_DIR", str(tmp_path))
        cross_encoder._state.update({"tried": False, "ok": False, "session": None, "vocab": None})
        assert cross_encoder.score("q", ["a", "b"]) is None
        assert cross_encoder.rerank("q", [{"content": "a"}, {"content": "b"}]) is None

    def test_import_error_is_swallowed(self, monkeypatch, tmp_path):
        from memory import cross_encoder

        monkeypatch.setitem(sys.modules, "onnxruntime", None)
        monkeypatch.setenv("JARVIS_RERANKER_DIR", str(tmp_path))
        (tmp_path / "vocab.txt").write_text("\n".join(VOCAB_LINES) + "\n", encoding="utf-8")
        (tmp_path / "model.onnx").write_bytes(b"x")
        cross_encoder._state.update({"tried": False, "ok": False, "session": None, "vocab": None})
        assert cross_encoder.available() is False

    def test_status_reports_fallback_backend(self, monkeypatch, tmp_path):
        from memory import cross_encoder

        monkeypatch.setenv("JARVIS_RERANKER_DIR", str(tmp_path / "absent"))
        monkeypatch.delenv("JARVIS_RERANKER", raising=False)
        cross_encoder._state.update({"tried": False, "ok": False, "session": None, "vocab": None})
        assert cross_encoder.status()["backend"] == "default-order"


class TestTokenizer:
    """WordPiece behaviour against a fixed synthetic vocabulary."""

    def test_known_words_are_lowercased_and_split(self, lane):
        assert lane._basic_tokens("User NAME") == ["user", "name"]

    def test_unknown_word_becomes_unk(self, lane):
        vocab = {"[CLS]": 2, "[SEP]": 3, "[UNK]": 1, "[PAD]": 0, "name": 6}
        assert lane._wordpiece("zzqx", vocab, 1) == [1]

    def test_overlong_word_becomes_unk(self, lane):
        vocab = {"[CLS]": 2, "[SEP]": 3, "[UNK]": 1, "[PAD]": 0}
        assert lane._wordpiece("a" * 200, vocab, 1) == [1]

    def test_punctuation_becomes_its_own_token(self, lane):
        assert lane._basic_tokens("hello, world!") == ["hello", ",", "world", "!"]

    def test_pair_has_cls_and_two_seps(self, lane):
        vocab = {"[CLS]": 2, "[SEP]": 3, "[UNK]": 1, "[PAD]": 0, "name": 6, "is": 7}
        ids, types, mask = lane._build_pair("what is my name", "name", vocab, 16)
        assert ids[0] == 2
        assert ids.count(3) == 2
        assert sum(mask) == 8
        assert ids[sum(mask):] == [0] * 8
        assert len(ids) == len(types) == len(mask) == 16

    def test_token_types_mark_the_document_segment(self, lane):
        vocab = {"[CLS]": 2, "[SEP]": 3, "[UNK]": 1, "[PAD]": 0, "name": 6}
        ids, types, mask = lane._build_pair("name", "name", vocab, 12)
        assert ids == [2, 6, 3, 6, 3] + [0] * 7
        assert types == [0, 0, 0, 1, 1] + [0] * 7
        assert mask == [1] * 5 + [0] * 7


class TestScoring:
    """Forward-pass plumbing, score mapping and ordering."""

    def test_masks_pad_and_token_types_are_correct(self, lane):
        import numpy as np

        lane.score("q", ["name is memory"])
        feed = sys.modules["onnxruntime"].last_feed
        assert feed["input_ids"].shape == feed["attention_mask"].shape
        assert feed["input_ids"].dtype == np.int64
        assert set(feed["token_type_ids"][0].tolist()) <= {0, 1}
        assert feed["attention_mask"].sum(axis=1).min() >= 2

    def test_scores_are_bounded_and_correct_length(self, lane):
        values = lane.score("what is my name", ["python project", "the user name is memory"])
        assert values is not None
        assert len(values) == 2
        assert all(0.0 <= v <= 1.0 for v in values)

    def test_scores_are_deterministic(self, lane):
        lane._cache.clear()
        first = lane.score("what is my name", ["the user name", "python project"])
        lane._cache.clear()
        assert lane.score("what is my name", ["the user name", "python project"]) == first

    def test_relevance_ordering(self, lane):
        values = lane.score("what is my name", ["python project", "the user name is memory"])
        assert values[1] > values[0]

    def test_rerank_puts_relevant_first(self, lane):
        memories = [
            {"content": "project uses python"},
            {"content": "the user name is memory"},
        ]
        result = lane.rerank("what is my name?", memories, max_results=2)
        assert result[0]["content"] == "the user name is memory"

    def test_rerank_respects_max_results(self, lane):
        memories = [{"content": f"memory number {i}"} for i in range(5)]
        assert len(lane.rerank("query", memories, max_results=2)) == 2

    def test_single_item_passthrough(self, lane):
        assert lane.rerank("query", [{"content": "only"}]) is None

    def test_cache_avoids_second_forward_pass(self, lane):
        lane.score("q", ["a name here"])
        assert len(lane._cache) == 1
        lane.score("q", ["a name here"])
        assert len(lane._cache) == 1


class TestControllerIntegration:
    """The retrieval path must honour lane ordering, not just filtering."""

    def _controller(self):
        from memory.controller import MemoryController

        return MemoryController.__new__(MemoryController)

    def _item(self, content):
        item = types.SimpleNamespace(content=content, type="note")
        item._signals = {"score": 0.0}
        return item

    def test_reranked_order_is_preserved(self, lane, monkeypatch):
        from memory import cross_encoder

        controller = self._controller()
        items = [self._item("project uses python"), self._item("the user name is memory")]
        out = controller._rerank_items("what is my name?", items, 2, use_llm_enhance=False)
        assert [i.content for i in out] == ["the user name is memory", "project uses python"]
        assert cross_encoder.status()["backend"] == "onnx-cross-encoder"

    def test_falls_back_to_input_order_when_lanes_fail(self, lane, monkeypatch):
        from memory import cross_encoder

        controller = self._controller()
        monkeypatch.setattr(cross_encoder, "rerank", lambda *a, **k: None, raising=False)
        items = [self._item("first"), self._item("second")]
        out = controller._rerank_items("q", items, 2, use_llm_enhance=False)
        assert [i.content for i in out] == ["first", "second"]

    def test_duplicate_content_is_not_dropped(self, lane):
        controller = self._controller()
        items = [self._item("same text"), self._item("same text")]
        out = controller._rerank_items("query", items, 2, use_llm_enhance=False)
        assert len(out) == 2

    def test_empty_and_single_short_circuit(self, lane):
        controller = self._controller()
        assert controller._rerank_items("q", [], 3, use_llm_enhance=False) == []
        single = [self._item("only")]
        assert controller._rerank_items("q", single, 3, use_llm_enhance=False) == single
