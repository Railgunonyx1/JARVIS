"""Conversation Flow Optimizer — Analyzes and improves conversation quality metrics."""

import logging
import math
import threading
from collections import Counter

logger = logging.getLogger("jarvis.interaction_engine.conversation_flow")


class ConversationFlowOptimizer:
    """Analyzes conversation flow quality and detects stalling patterns."""

    def __init__(self):
        self._lock = threading.Lock()
        self._metrics_history: list[dict] = []
        self._total_conversations: int = 0
        self._total_turns: int = 0
        self._total_engagement: float = 0.0

    def analyze_flow(self, history: list) -> dict:
        """Analyze conversation flow quality from message history.

        Each history entry should have at least 'text' and optionally 'role', 'intent'.
        """
        if not history:
            return {
                "turns": 0,
                "avg_response_length": 0.0,
                "topic_changes": 0,
                "engagement_score": 0.0,
            }

        turns = len(history)
        lengths = []
        intents = []
        roles = []

        for entry in history:
            if isinstance(entry, dict):
                text = entry.get("text", entry.get("message", ""))
                lengths.append(len(text.split()))
                intent = entry.get("intent", "")
                if intent:
                    intents.append(intent)
                roles.append(entry.get("role", "unknown"))
            elif isinstance(entry, str):
                lengths.append(len(entry.split()))

        avg_length = sum(lengths) / len(lengths) if lengths else 0.0

        topic_changes = 0
        for i in range(1, len(intents)):
            if intents[i] != intents[i - 1]:
                topic_changes += 1

        engagement_score = self._compute_engagement(
            turns=turns,
            avg_length=avg_length,
            topic_changes=topic_changes,
            lengths=lengths,
            roles=roles,
        )

        return {
            "turns": turns,
            "avg_response_length": round(avg_length, 2),
            "topic_changes": topic_changes,
            "engagement_score": round(engagement_score, 4),
        }

    def suggest_improvements(self, flow_analysis: dict) -> list[str]:
        """Suggest conversation flow improvements based on analysis."""
        suggestions = []
        turns = flow_analysis.get("turns", 0)
        avg_length = flow_analysis.get("avg_response_length", 0.0)
        topic_changes = flow_analysis.get("topic_changes", 0)
        engagement = flow_analysis.get("engagement_score", 0.0)

        if turns <= 1:
            suggestions.append("Conversation is very short. Consider asking follow-up questions to deepen engagement.")
        elif turns > 30:
            suggestions.append("Conversation is lengthy. Consider summarizing progress and checking if the user needs anything else.")

        if avg_length < 3:
            suggestions.append("Responses are very terse. Consider providing more context or detail in replies.")
        elif avg_length > 100:
            suggestions.append("Responses are very long. Consider being more concise to maintain readability.")

        if topic_changes == 0 and turns > 3:
            suggestions.append("No topic changes detected. The conversation may be stale — consider introducing a new topic.")
        elif topic_changes > turns * 0.8 and turns > 4:
            suggestions.append("Frequent topic changes. Consider staying on topic longer for deeper exploration.")

        if engagement < 0.3:
            suggestions.append("Engagement is low. Try asking open-ended questions or offering specific suggestions.")
        elif engagement > 0.8:
            suggestions.append("Engagement is high. Maintain the current conversational approach.")

        if not suggestions:
            suggestions.append("Conversation flow looks healthy. No changes recommended.")

        return suggestions

    def detect_stalling(self, history: list, threshold: int = 3) -> bool:
        """Detect if conversation is stalling (repeated similar intents)."""
        if len(history) < threshold:
            return False

        recent_intents = []
        for entry in history[-threshold:]:
            if isinstance(entry, dict):
                intent = entry.get("intent", entry.get("text", ""))
                recent_intents.append(intent)
            elif isinstance(entry, str):
                recent_intents.append(entry)

        if not recent_intents:
            return False

        if len(set(recent_intents)) == 1 and recent_intents[0]:
            return True

        # Also detect stalling by repeated very short messages
        recent_lengths = []
        for entry in history[-threshold:]:
            if isinstance(entry, dict):
                text = entry.get("text", entry.get("message", ""))
                recent_lengths.append(len(text.split()))
            elif isinstance(entry, str):
                recent_lengths.append(len(entry.split()))

        if recent_lengths and all(length <= 2 for length in recent_lengths):
            return True

        return False

    def get_conversation_metrics(self) -> dict:
        """Return overall conversation metrics across all recorded sessions."""
        with self._lock:
            total_conversations = self._total_conversations
            total_turns = self._total_turns
            avg_engagement = self._total_engagement / total_conversations if total_conversations > 0 else 0.0
            recent = self._metrics_history[-100:] if self._metrics_history else []

        recent_avg_turns = 0.0
        recent_avg_engagement = 0.0
        if recent:
            recent_avg_turns = sum(m.get("turns", 0) for m in recent) / len(recent)
            recent_avg_engagement = sum(m.get("engagement_score", 0) for m in recent) / len(recent)

        return {
            "total_conversations": total_conversations,
            "total_turns": total_turns,
            "avg_turns_per_conversation": round(total_turns / total_conversations, 2) if total_conversations > 0 else 0.0,
            "avg_engagement_score": round(avg_engagement, 4),
            "recent_avg_turns": round(recent_avg_turns, 2),
            "recent_avg_engagement": round(recent_avg_engagement, 4),
            "metrics_history_size": len(self._metrics_history),
        }

    def record_metrics(self, metrics: dict) -> None:
        """Record conversation metrics for a completed conversation."""
        with self._lock:
            self._metrics_history.append(metrics)
            if len(self._metrics_history) > 1000:
                self._metrics_history = self._metrics_history[-500:]

            self._total_conversations += 1
            self._total_turns += metrics.get("turns", 0)
            self._total_engagement += metrics.get("engagement_score", 0.0)

    def _compute_engagement(self, turns: int, avg_length: float,
                            topic_changes: int, lengths: list, roles: list) -> float:
        """Compute an engagement score from 0.0 to 1.0."""
        score = 0.0

        # Turn contribution: more turns = more engaged, diminishing returns
        if turns > 0:
            turn_score = min(math.log2(turns + 1) / 6.0, 1.0)
            score += turn_score * 0.3

        # Length contribution: moderate length is best
        if avg_length > 0:
            if avg_length <= 5:
                length_score = avg_length / 5.0 * 0.5
            elif avg_length <= 50:
                length_score = 0.5 + (avg_length - 5) / 45.0 * 0.5
            else:
                length_score = max(1.0 - (avg_length - 50) / 100.0, 0.3)
            score += length_score * 0.25

        # Topic diversity contribution
        if turns > 1:
            diversity = topic_changes / (turns - 1)
            # Moderate diversity is ideal (0.2-0.5)
            if 0.2 <= diversity <= 0.5:
                diversity_score = 1.0
            elif diversity < 0.2:
                diversity_score = diversity / 0.2 * 0.8 if diversity > 0 else 0.1
            else:
                diversity_score = max(1.0 - (diversity - 0.5), 0.3)
            score += diversity_score * 0.25

        # Balance contribution: check if both user and assistant participate
        if roles:
            role_counts = Counter(roles)
            if len(role_counts) > 1:
                min_count = min(role_counts.values())
                max_count = max(role_counts.values())
                balance = min_count / max_count if max_count > 0 else 0
                score += balance * 0.2
            else:
                score += 0.05
        else:
            score += 0.1

        return min(score, 1.0)


_instance: ConversationFlowOptimizer | None = None
_instance_lock = threading.Lock()


def get_conversation_flow_optimizer() -> ConversationFlowOptimizer:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ConversationFlowOptimizer()
    return _instance
