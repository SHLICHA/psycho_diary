"""
Локальная кластеризация элементов профильных полей через sentence-transformers.

Сервис работает по одному list-полю за раз, объединяет семантически близкие
элементы и сохраняет weighted-формат без искусственных count-limits.
"""

import logging
import os
import re
from datetime import date, datetime, timezone as dt_timezone
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core.profile_field_utils import convert_to_weighted_format

logger = logging.getLogger(__name__)


DEFAULT_MODEL_NAME = os.getenv(
    "SENTENCE_TRANSFORMERS_MODEL_NAME",
    "ai-forever/sbert_large_nlu_ru",
)
DEFAULT_DEVICE = os.getenv("SENTENCE_TRANSFORMERS_DEVICE", "cpu")
DEFAULT_SIMILARITY_THRESHOLD = float(os.getenv("PROFILE_CLUSTER_SIMILARITY_THRESHOLD", "0.78"))
FIELD_THRESHOLD_ENV_KEYS = {
    "life_facts": "PROFILE_CLUSTER_SIMILARITY_THRESHOLD_LIFE_FACTS",
    "hobbies": "PROFILE_CLUSTER_SIMILARITY_THRESHOLD_HOBBIES",
    "core_values": "PROFILE_CLUSTER_SIMILARITY_THRESHOLD_CORE_VALUES",
    "triggers": "PROFILE_CLUSTER_SIMILARITY_THRESHOLD_TRIGGERS",
    "strengths": "PROFILE_CLUSTER_SIMILARITY_THRESHOLD_STRENGTHS",
    "areas_for_growth": "PROFILE_CLUSTER_SIMILARITY_THRESHOLD_AREAS_FOR_GROWTH",
    "practical_patterns": "PROFILE_CLUSTER_SIMILARITY_THRESHOLD_PRACTICAL_PATTERNS",
    "aspirations": "PROFILE_CLUSTER_SIMILARITY_THRESHOLD_ASPIRATIONS",
}
FIELD_THRESHOLD_DEFAULTS = {
    "life_facts": 0.79,
    "hobbies": 0.82,
    "core_values": 0.84,
    "triggers": 0.78,
    "strengths": 0.80,
    "areas_for_growth": 0.80,
    "practical_patterns": 0.80,
    "aspirations": 0.82,
}


@dataclass(frozen=True)
class _ClusterSeed:
    index: int
    value: str
    weight: float
    frequency: int
    is_stale: bool
    added_at: Optional[str]
    last_seen: Optional[str]


class LocalProfileClusterService:
    """Кластеризует элементы одного профильного поля локальной моделью."""

    def __init__(self) -> None:
        self._model = None
        self._model_error: Optional[str] = None
        self._lock = Lock()

    def cluster_items(
        self,
        items: List[Any],
        *,
        field_name: str,
        similarity_threshold: Optional[float] = None,
    ) -> Dict[str, Any]:
        prepared_items = convert_to_weighted_format(items or [])
        if not prepared_items:
            return {
                "field_name": field_name,
                "cleaned_items": [],
                "used_fallback": False,
                "error": None,
                "strategy": "empty",
            }

        threshold = self._resolve_similarity_threshold(
            field_name=field_name,
            explicit_value=similarity_threshold,
        )
        seeds = self._prepare_seeds(prepared_items)
        if len(seeds) == 1:
            return {
                "field_name": field_name,
                "cleaned_items": self._seeds_to_weighted_items(seeds),
                "used_fallback": False,
                "error": None,
                "strategy": "single_item",
            }

        model = self._load_model()
        if model is None:
            raise RuntimeError(self._model_error or "sentence_transformers_model_unavailable")

        embeddings = model.encode(
            [seed.value for seed in seeds],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        if not isinstance(embeddings, np.ndarray):
            embeddings = np.asarray(embeddings, dtype=np.float32)

        clusters = self._cluster_by_similarity(seeds, embeddings, threshold=threshold)
        cleaned_items = self._merge_clusters(seeds, clusters)

        logger.debug(
            "[LocalProfileCluster] field=%s, input=%s, output=%s, threshold=%.2f",
            field_name,
            len(prepared_items),
            len(cleaned_items),
            threshold,
        )

        return {
            "field_name": field_name,
            "cleaned_items": cleaned_items,
            "used_fallback": False,
            "error": None,
            "strategy": "sentence_transformers",
        }

    def _resolve_similarity_threshold(self, *, field_name: str, explicit_value: Optional[float]) -> float:
        if explicit_value is not None:
            return explicit_value

        env_key = FIELD_THRESHOLD_ENV_KEYS.get(field_name)
        default_for_field = FIELD_THRESHOLD_DEFAULTS.get(field_name, DEFAULT_SIMILARITY_THRESHOLD)
        if env_key is None:
            return default_for_field

        raw_value = os.getenv(env_key)
        if raw_value is None:
            return default_for_field

        try:
            return float(raw_value)
        except ValueError:
            logger.warning(
                "[LocalProfileCluster] Invalid threshold in %s=%s, using default %.2f",
                env_key,
                raw_value,
                default_for_field,
            )
            return default_for_field

    def _load_model(self):
        if self._model is not None:
            return self._model
        if self._model_error is not None:
            return None

        with self._lock:
            if self._model is not None:
                return self._model
            if self._model_error is not None:
                return None

            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(DEFAULT_MODEL_NAME, device=DEFAULT_DEVICE)
                logger.info(
                    "[LocalProfileCluster] Model loaded: %s on %s",
                    DEFAULT_MODEL_NAME,
                    DEFAULT_DEVICE,
                )
                return self._model
            except Exception as exc:
                self._model_error = str(exc)
                logger.error(
                    "[LocalProfileCluster] Failed to load model '%s': %s",
                    DEFAULT_MODEL_NAME,
                    exc,
                    exc_info=True,
                )
                return None

    def _prepare_seeds(self, items: List[Dict[str, Any]]) -> List[_ClusterSeed]:
        seeds: List[_ClusterSeed] = []
        for index, item in enumerate(items):
            value = str(item.get("value", "")).strip()
            if not value:
                continue
            seeds.append(
                _ClusterSeed(
                    index=index,
                    value=value,
                    weight=float(item.get("weight", 0.5) or 0.5),
                    frequency=int(item.get("frequency", 1) or 1),
                    is_stale=bool(item.get("is_stale", False)),
                    added_at=self._normalize_date(item.get("added_at")),
                    last_seen=self._normalize_date(item.get("last_seen")),
                )
            )
        return seeds

    def _seeds_to_weighted_items(self, seeds: List[_ClusterSeed]) -> List[Dict[str, Any]]:
        return [
            {
                "value": seed.value,
                "weight": seed.weight,
                "frequency": seed.frequency,
                "is_stale": seed.is_stale,
                "added_at": seed.added_at or self._today_iso(),
                "last_seen": seed.last_seen or self._today_iso(),
            }
            for seed in seeds
        ]

    def _cluster_by_similarity(
        self,
        seeds: List[_ClusterSeed],
        embeddings: np.ndarray,
        *,
        threshold: float,
    ) -> List[List[int]]:
        parent = list(range(len(seeds)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            root_left = find(left)
            root_right = find(right)
            if root_left != root_right:
                parent[root_right] = root_left

        for left in range(len(seeds)):
            for right in range(left + 1, len(seeds)):
                if self._is_similar(
                    seeds[left].value,
                    seeds[right].value,
                    embeddings[left],
                    embeddings[right],
                    threshold,
                ):
                    union(left, right)

        grouped: Dict[int, List[int]] = {}
        for index in range(len(seeds)):
            grouped.setdefault(find(index), []).append(index)

        clusters = list(grouped.values())
        clusters.sort(key=lambda cluster: min(seeds[index].index for index in cluster))
        return clusters

    def _is_similar(
        self,
        left_value: str,
        right_value: str,
        left_embedding: np.ndarray,
        right_embedding: np.ndarray,
        threshold: float,
    ) -> bool:
        left_key = self._canonical_key(left_value)
        right_key = self._canonical_key(right_value)
        if left_key and left_key == right_key:
            return True

        similarity = float(np.dot(left_embedding, right_embedding))
        if similarity >= threshold:
            return True

        # Дополнительный мягкий сигнал для очевидных переформулировок.
        return self._token_jaccard(left_key, right_key) >= 0.6

    def _merge_clusters(
        self,
        seeds: List[_ClusterSeed],
        clusters: List[List[int]],
    ) -> List[Dict[str, Any]]:
        merged_items: List[Dict[str, Any]] = []
        for cluster in clusters:
            cluster_seeds = [seeds[index] for index in cluster]
            representative = self._pick_representative(cluster_seeds)
            merged_items.append(
                {
                    "value": representative.value,
                    "weight": max(seed.weight for seed in cluster_seeds),
                    "frequency": sum(seed.frequency for seed in cluster_seeds),
                    "is_stale": all(seed.is_stale for seed in cluster_seeds),
                    "added_at": self._pick_earliest_added_at(cluster_seeds),
                    "last_seen": self._pick_latest_last_seen(cluster_seeds),
                }
            )

        merged_items.sort(key=lambda item: (-float(item["weight"]), -int(item["frequency"]), item["value"]))
        return merged_items

    def _pick_representative(self, cluster: List[_ClusterSeed]) -> _ClusterSeed:
        if len(cluster) == 1:
            return cluster[0]

        candidate_scores: List[Tuple[float, _ClusterSeed]] = []
        for candidate in cluster:
            score = candidate.weight * 2.0 + candidate.frequency + (len(candidate.value) / 100.0)
            candidate_scores.append((score, candidate))

        candidate_scores.sort(key=lambda item: (-item[0], item[1].index))
        return candidate_scores[0][1]

    def _pick_earliest_added_at(self, cluster: List[_ClusterSeed]) -> Optional[str]:
        return self._pick_datetime_value([seed.added_at for seed in cluster], strategy="min")

    def _pick_latest_last_seen(self, cluster: List[_ClusterSeed]) -> Optional[str]:
        return self._pick_datetime_value([seed.last_seen for seed in cluster], strategy="max")

    def _pick_datetime_value(self, values: List[Optional[str]], *, strategy: str) -> Optional[str]:
        normalized: List[datetime] = []
        for value in values:
            parsed = self._to_datetime(value)
            if parsed is not None:
                normalized.append(parsed)

        if not normalized:
            return None

        if strategy == "min":
            return min(normalized).isoformat()
        if strategy == "max":
            return max(normalized).isoformat()
        raise ValueError(f"Unknown datetime pick strategy: {strategy}")

    def _canonical_key(self, value: str) -> str:
        normalized = re.sub(r"\s+", " ", value.strip().lower())
        return re.sub(r"[^\w\s]", "", normalized)

    def _token_jaccard(self, left_key: str, right_key: str) -> float:
        left_tokens = {token for token in left_key.split() if len(token) > 2}
        right_tokens = {token for token in right_key.split() if len(token) > 2}
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = len(left_tokens & right_tokens)
        union = len(left_tokens | right_tokens)
        return intersection / union if union else 0.0

    def _normalize_date(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            raw = value.strip()
            return raw or None
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                return None
        return None

    def _to_datetime(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None

        parsed: Optional[datetime] = None
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, date):
            parsed = datetime.combine(value, datetime.min.time())
        elif isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                try:
                    parsed_date = date.fromisoformat(raw)
                    parsed = datetime.combine(parsed_date, datetime.min.time())
                except ValueError:
                    return None
        else:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt_timezone.utc)
        else:
            parsed = parsed.astimezone(dt_timezone.utc)
        return parsed

    def _today_iso(self) -> str:
        from django.utils import timezone

        return timezone.now().date().isoformat()


local_profile_cluster_service = LocalProfileClusterService()
