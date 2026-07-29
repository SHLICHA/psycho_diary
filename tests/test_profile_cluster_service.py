"""Тесты для локальной кластеризации профильных полей."""

import numpy as np
import pytest

from diary.services.profile_cluster_service import LocalProfileClusterService


class _FakeEmbeddingModel:
    def __init__(self, mapping):
        self.mapping = mapping

    def encode(self, texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False):
        vectors = [self.mapping[text] for text in texts]
        array = np.asarray(vectors, dtype=np.float32)
        if normalize_embeddings:
            norms = np.linalg.norm(array, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            array = array / norms
        return array


@pytest.mark.django_db
class TestLocalProfileClusterService:
    def test_cluster_items_merges_semantic_duplicates(self):
        service = LocalProfileClusterService()
        fake_model = _FakeEmbeddingModel(
            {
                "тревога": [1.0, 0.0, 0.0],
                "утренняя тревога": [0.97, 0.03, 0.0],
                "спорт": [0.0, 1.0, 0.0],
                "бег": [0.0, 0.0, 1.0],
            }
        )
        service._load_model = lambda: fake_model

        result = service.cluster_items(
            [
                {"value": "тревога", "weight": 0.9, "frequency": 2, "is_stale": False},
                {"value": "утренняя тревога", "weight": 0.7, "frequency": 1, "is_stale": False},
                {"value": "спорт", "weight": 0.8, "frequency": 4, "is_stale": False},
                "бег",
            ],
            field_name="triggers",
        )

        assert result["strategy"] == "sentence_transformers"
        assert len(result["cleaned_items"]) == 3

        merged_triggers = next(item for item in result["cleaned_items"] if "тревога" in item["value"])
        assert merged_triggers["weight"] == pytest.approx(0.9)
        assert merged_triggers["frequency"] == 3
        assert merged_triggers["is_stale"] is False

    def test_cluster_items_returns_empty_payload_for_empty_input(self):
        service = LocalProfileClusterService()

        result = service.cluster_items([], field_name="hobbies")

        assert result["strategy"] == "empty"
        assert result["cleaned_items"] == []

    def test_cluster_items_datetime_aggregation_uses_real_time_order(self):
        service = LocalProfileClusterService()
        fake_model = _FakeEmbeddingModel(
            {
                "тревожность": [1.0, 0.0],
                "социальная тревожность": [0.99, 0.01],
            }
        )
        service._load_model = lambda: fake_model

        result = service.cluster_items(
            [
                {
                    "value": "тревожность",
                    "weight": 0.7,
                    "frequency": 2,
                    "added_at": "2026-04-18T23:00:00-05:00",
                    "last_seen": "2026-04-20T01:00:00+00:00",
                    "is_stale": False,
                },
                {
                    "value": "социальная тревожность",
                    "weight": 0.8,
                    "frequency": 3,
                    "added_at": "2026-04-19T01:00:00+00:00",
                    "last_seen": "2026-04-20T03:30:00+03:00",
                    "is_stale": False,
                },
            ],
            field_name="triggers",
        )

        assert len(result["cleaned_items"]) == 1
        merged = result["cleaned_items"][0]
        assert merged["frequency"] == 5
        assert merged["added_at"].startswith("2026-04-19T01:00:00")
        assert merged["last_seen"].startswith("2026-04-20T01:00:00")
