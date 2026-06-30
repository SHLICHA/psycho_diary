"""Unit tests for PrometheusFormatter."""

import pytest
from core.services.prometheus_formatter import PrometheusFormatter


class TestPrometheusFormatterEscaping:
    """Test label value escaping for Prometheus format."""
    
    def test_escape_backslash(self):
        """Backslashes should be escaped."""
        result = PrometheusFormatter._escape_label_value("path\\to\\file")
        assert result == "path\\\\to\\\\file"
    
    def test_escape_newline(self):
        """Newlines should be escaped."""
        result = PrometheusFormatter._escape_label_value("line1\nline2")
        assert result == "line1\\nline2"
    
    def test_escape_quote(self):
        """Double quotes should be escaped."""
        result = PrometheusFormatter._escape_label_value('say "hello"')
        assert result == 'say \\"hello\\"'
    
    def test_escape_combined(self):
        """Multiple special characters should all be escaped."""
        result = PrometheusFormatter._escape_label_value('path\\to\n"file"')
        assert result == 'path\\\\to\\n\\"file\\"'
    
    def test_escape_normal_text(self):
        """Normal text should not be changed."""
        result = PrometheusFormatter._escape_label_value("normal_event_name")
        assert result == "normal_event_name"


class TestPrometheusFormatterCounter:
    """Test counter formatting."""
    
    def test_format_counter_with_labels(self):
        """Counter with labels should have proper format."""
        result = PrometheusFormatter._format_counter(
            "test_metric",
            42,
            {"label1": "value1", "label2": "value2"}
        )
        # Order might vary, so check both orders
        assert "test_metric{" in result
        assert 'label1="value1"' in result
        assert 'label2="value2"' in result
        assert "} 42.0\n" in result
    
    def test_format_counter_without_labels(self):
        """Counter without labels should have simple format."""
        result = PrometheusFormatter._format_counter("test_metric", 100)
        assert result == "test_metric 100.0\n"
    
    def test_format_counter_float_value(self):
        """Float values should be formatted correctly."""
        result = PrometheusFormatter._format_counter("test_metric", 123.456)
        assert result == "test_metric 123.456\n"
    
    def test_format_counter_zero_value(self):
        """Zero values should be formatted correctly."""
        result = PrometheusFormatter._format_counter("test_metric", 0)
        assert result == "test_metric 0.0\n"


class TestPrometheusFormatterSnapshot:
    """Test snapshot to Prometheus format conversion."""
    
    def test_format_empty_snapshot(self):
        """Empty snapshot should produce valid Prometheus output."""
        snapshot = {
            "use_cases": {},
            "ai_calls": {},
            "transport": {},
            "totals": {"success": 0, "failure": 0},
        }
        result = PrometheusFormatter.format_snapshot(snapshot)
        
        # Check that HELP and TYPE comments are present
        assert "# HELP" in result
        assert "# TYPE" in result
        assert "psycho_diary_total_success_total 0.0" in result
        assert "psycho_diary_total_failure_total 0.0" in result
    
    def test_format_snapshot_with_use_cases(self):
        """Snapshot with use case metrics should be formatted correctly."""
        snapshot = {
            "use_cases": {
                "new_entry": {
                    "count": 10,
                    "success": 8,
                    "failure": 2,
                    "last_duration_ms": 150.5,
                    "last_metadata": {},
                }
            },
            "ai_calls": {},
            "transport": {},
            "totals": {"success": 8, "failure": 2},
        }
        result = PrometheusFormatter.format_snapshot(snapshot)
        
        # Check use case metrics
        assert 'psycho_diary_use_cases_total{use_case="new_entry"} 10.0' in result
        assert 'psycho_diary_use_cases_success_total{use_case="new_entry"} 8.0' in result
        assert 'psycho_diary_use_cases_failure_total{use_case="new_entry"} 2.0' in result
        assert 'psycho_diary_use_cases_last_duration_ms{use_case="new_entry"} 150.5' in result
        
        # Check totals
        assert "psycho_diary_total_success_total 8.0" in result
        assert "psycho_diary_total_failure_total 2.0" in result
    
    def test_format_snapshot_with_ai_calls(self):
        """Snapshot with AI call metrics should be formatted correctly."""
        snapshot = {
            "use_cases": {},
            "ai_calls": {
                "deepseek_analysis": {
                    "count": 5,
                    "success": 4,
                    "failure": 1,
                    "last_duration_ms": 2500.0,
                    "last_metadata": {"tokens": 1500},
                }
            },
            "transport": {},
            "totals": {"success": 4, "failure": 1},
        }
        result = PrometheusFormatter.format_snapshot(snapshot)
        
        # Check AI call metrics
        assert 'psycho_diary_ai_calls_total{flow="deepseek_analysis"} 5.0' in result
        assert 'psycho_diary_ai_calls_success_total{flow="deepseek_analysis"} 4.0' in result
        assert 'psycho_diary_ai_calls_failure_total{flow="deepseek_analysis"} 1.0' in result
        assert 'psycho_diary_ai_calls_last_duration_ms{flow="deepseek_analysis"} 2500.0' in result
    
    def test_format_snapshot_with_transport(self):
        """Snapshot with transport metrics should be formatted correctly."""
        snapshot = {
            "use_cases": {},
            "ai_calls": {},
            "transport": {
                "telegram_message": {
                    "count": 100,
                    "success": 95,
                    "failure": 5,
                    "last_duration_ms": 50.0,
                    "last_metadata": {},
                }
            },
            "totals": {"success": 95, "failure": 5},
        }
        result = PrometheusFormatter.format_snapshot(snapshot)
        
        # Check transport metrics
        assert 'psycho_diary_transport_events_total{event="telegram_message"} 100.0' in result
        assert 'psycho_diary_transport_events_success_total{event="telegram_message"} 95.0' in result
        assert 'psycho_diary_transport_events_failure_total{event="telegram_message"} 5.0' in result
        assert 'psycho_diary_transport_events_last_duration_ms{event="telegram_message"} 50.0' in result
    
    def test_format_snapshot_multiple_metrics_per_bucket(self):
        """Snapshot with multiple metrics in same bucket."""
        snapshot = {
            "use_cases": {
                "new_entry": {
                    "count": 10,
                    "success": 8,
                    "failure": 2,
                    "last_duration_ms": 150.0,
                    "last_metadata": {},
                },
                "clarify_entry": {
                    "count": 5,
                    "success": 4,
                    "failure": 1,
                    "last_duration_ms": 100.0,
                    "last_metadata": {},
                },
            },
            "ai_calls": {},
            "transport": {},
            "totals": {"success": 12, "failure": 3},
        }
        result = PrometheusFormatter.format_snapshot(snapshot)
        
        # Check both use cases are present
        assert 'psycho_diary_use_cases_total{use_case="new_entry"} 10.0' in result
        assert 'psycho_diary_use_cases_total{use_case="clarify_entry"} 5.0' in result
    
    def test_format_snapshot_with_special_chars_in_names(self):
        """Metric names with special characters should be properly escaped."""
        snapshot = {
            "use_cases": {
                'event_with_"quote"': {
                    "count": 1,
                    "success": 1,
                    "failure": 0,
                    "last_duration_ms": 100.0,
                    "last_metadata": {},
                }
            },
            "ai_calls": {},
            "transport": {},
            "totals": {"success": 1, "failure": 0},
        }
        result = PrometheusFormatter.format_snapshot(snapshot)
        
        # Check that special chars are escaped
        assert 'use_case="event_with_\\"quote\\""' in result
    
    def test_format_snapshot_output_format(self):
        """Output should be valid Prometheus exposition format."""
        snapshot = {
            "use_cases": {
                "test_event": {
                    "count": 1,
                    "success": 1,
                    "failure": 0,
                    "last_duration_ms": 10.0,
                    "last_metadata": {},
                }
            },
            "ai_calls": {},
            "transport": {},
            "totals": {"success": 1, "failure": 0},
        }
        result = PrometheusFormatter.format_snapshot(snapshot)
        
        # Should be a string
        assert isinstance(result, str)
        
        # Should contain newlines
        assert "\n" in result
        
        # Should start with comment (HELP or TYPE)
        lines = result.strip().split("\n")
        assert lines[0].startswith("#")
        
        # Should have data lines with values
        has_data_line = False
        for line in lines:
            if "psycho_diary" in line and not line.startswith("#"):
                has_data_line = True
                break
        assert has_data_line

    def test_format_snapshot_with_max_runtime_diagnostics(self):
        """MAX runtime diagnostic gauges should be present and derived from transport metadata."""
        snapshot = {
            "use_cases": {},
            "ai_calls": {},
            "transport": {
                "max_runtime_polling_iteration": {
                    "count": 4,
                    "success": 4,
                    "failure": 0,
                    "last_duration_ms": 321.5,
                    "last_metadata": {"updates_count": 3},
                },
                "max_runtime_webhook_register": {
                    "count": 1,
                    "success": 1,
                    "failure": 0,
                    "last_duration_ms": 22.0,
                    "last_metadata": {"outcome": "success"},
                },
            },
            "totals": {"success": 5, "failure": 0},
        }
        result = PrometheusFormatter.format_snapshot(snapshot)

        assert 'psycho_diary_max_runtime_polling_lag_ms 321.5' in result
        assert 'psycho_diary_max_runtime_polling_last_updates_count 3.0' in result
        assert 'psycho_diary_max_runtime_webhook_register_outcome 1.0' in result
