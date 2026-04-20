"""Prometheus text format (exposition format) formatter for monitoring metrics."""

from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)


class PrometheusFormatter:
    """Converts monitoring service snapshot to Prometheus exposition format."""
    
    # Prometheus metric name prefix
    PREFIX = "psycho_diary"
    
    # Metrics per bucket type
    METRICS_TEMPLATE = {
        "use_cases": {
            "count_metric": "{prefix}_use_cases_total",
            "success_metric": "{prefix}_use_cases_success_total",
            "failure_metric": "{prefix}_use_cases_failure_total",
            "duration_metric": "{prefix}_use_cases_last_duration_ms",
            "label": "use_case",
        },
        "ai_calls": {
            "count_metric": "{prefix}_ai_calls_total",
            "success_metric": "{prefix}_ai_calls_success_total",
            "failure_metric": "{prefix}_ai_calls_failure_total",
            "duration_metric": "{prefix}_ai_calls_last_duration_ms",
            "label": "flow",
        },
        "transport": {
            "count_metric": "{prefix}_transport_events_total",
            "success_metric": "{prefix}_transport_events_success_total",
            "failure_metric": "{prefix}_transport_events_failure_total",
            "duration_metric": "{prefix}_transport_events_last_duration_ms",
            "label": "event",
        },
    }
    
    @staticmethod
    def _escape_label_value(value: str) -> str:
        """Escape label value for Prometheus format."""
        # Escape backslashes first, then newlines, quotes
        value = str(value).replace("\\", "\\\\")
        value = value.replace("\n", "\\n")
        value = value.replace('"', '\\"')
        return value
    
    @staticmethod
    def _format_counter(
        name: str,
        value: Any,
        labels: Dict[str, str] | None = None,
    ) -> str:
        """Format a single counter metric line."""
        if labels:
            label_str = ",".join(
                f'{k}="{PrometheusFormatter._escape_label_value(v)}"'
                for k, v in labels.items()
            )
            return f'{name}{{{label_str}}} {float(value)}\n'
        return f'{name} {float(value)}\n'
    
    @classmethod
    def _format_bucket_metrics(
        cls,
        bucket_name: str,
        bucket_data: Dict[str, Any],
    ) -> str:
        """Format metrics from a single bucket (use_cases, ai_calls, transport)."""
        output = ""
        template = cls.METRICS_TEMPLATE[bucket_name]
        label_name = template["label"]
        
        # Format each event in the bucket
        for event_name, event_data in bucket_data.items():
            labels = {label_name: event_name}
            
            # Count (total events)
            output += cls._format_counter(
                template["count_metric"].format(prefix=cls.PREFIX),
                event_data.get("count", 0),
                labels,
            )
            
            # Success count
            output += cls._format_counter(
                template["success_metric"].format(prefix=cls.PREFIX),
                event_data.get("success", 0),
                labels,
            )
            
            # Failure count
            output += cls._format_counter(
                template["failure_metric"].format(prefix=cls.PREFIX),
                event_data.get("failure", 0),
                labels,
            )
            
            # Last duration
            output += cls._format_counter(
                template["duration_metric"].format(prefix=cls.PREFIX),
                event_data.get("last_duration_ms", 0),
                labels,
            )
        
        return output
    
    @classmethod
    def format_snapshot(cls, snapshot: Dict[str, Any]) -> str:
        """
        Convert monitoring snapshot to Prometheus exposition format.
        
        Args:
            snapshot: Dictionary from monitoring_service.get_snapshot()
        
        Returns:
            Prometheus text format string (UTF-8 encoded text)
        """
        try:
            output = ""
            
            # Add HELP and TYPE comments for each bucket
            output += f"# HELP {cls.PREFIX}_use_cases_total Total count of use case executions\n"
            output += f"# TYPE {cls.PREFIX}_use_cases_total counter\n"
            output += f"# HELP {cls.PREFIX}_use_cases_success_total Successful use case executions\n"
            output += f"# TYPE {cls.PREFIX}_use_cases_success_total counter\n"
            output += f"# HELP {cls.PREFIX}_use_cases_failure_total Failed use case executions\n"
            output += f"# TYPE {cls.PREFIX}_use_cases_failure_total counter\n"
            output += f"# HELP {cls.PREFIX}_use_cases_last_duration_ms Last duration of use case execution in milliseconds\n"
            output += f"# TYPE {cls.PREFIX}_use_cases_last_duration_ms gauge\n"
            
            output += f"# HELP {cls.PREFIX}_ai_calls_total Total count of AI provider calls\n"
            output += f"# TYPE {cls.PREFIX}_ai_calls_total counter\n"
            output += f"# HELP {cls.PREFIX}_ai_calls_success_total Successful AI provider calls\n"
            output += f"# TYPE {cls.PREFIX}_ai_calls_success_total counter\n"
            output += f"# HELP {cls.PREFIX}_ai_calls_failure_total Failed AI provider calls\n"
            output += f"# TYPE {cls.PREFIX}_ai_calls_failure_total counter\n"
            output += f"# HELP {cls.PREFIX}_ai_calls_last_duration_ms Last duration of AI provider call in milliseconds\n"
            output += f"# TYPE {cls.PREFIX}_ai_calls_last_duration_ms gauge\n"
            
            output += f"# HELP {cls.PREFIX}_transport_events_total Total count of transport events\n"
            output += f"# TYPE {cls.PREFIX}_transport_events_total counter\n"
            output += f"# HELP {cls.PREFIX}_transport_events_success_total Successful transport events\n"
            output += f"# TYPE {cls.PREFIX}_transport_events_success_total counter\n"
            output += f"# HELP {cls.PREFIX}_transport_events_failure_total Failed transport events\n"
            output += f"# TYPE {cls.PREFIX}_transport_events_failure_total counter\n"
            output += f"# HELP {cls.PREFIX}_transport_events_last_duration_ms Last duration of transport event in milliseconds\n"
            output += f"# TYPE {cls.PREFIX}_transport_events_last_duration_ms gauge\n"
            
            output += f"# HELP {cls.PREFIX}_total_success_total Total successful events across all buckets\n"
            output += f"# TYPE {cls.PREFIX}_total_success_total counter\n"
            output += f"# HELP {cls.PREFIX}_total_failure_total Total failed events across all buckets\n"
            output += f"# TYPE {cls.PREFIX}_total_failure_total counter\n"
            
            # Format bucket metrics
            output += "\n"
            output += cls._format_bucket_metrics("use_cases", snapshot.get("use_cases", {}))
            output += cls._format_bucket_metrics("ai_calls", snapshot.get("ai_calls", {}))
            output += cls._format_bucket_metrics("transport", snapshot.get("transport", {}))
            
            # Format totals
            totals = snapshot.get("totals", {})
            output += cls._format_counter(
                f"{cls.PREFIX}_total_success_total",
                totals.get("success", 0),
            )
            output += cls._format_counter(
                f"{cls.PREFIX}_total_failure_total",
                totals.get("failure", 0),
            )
            
            return output
        except Exception as exc:
            logger.error("[prometheus_formatter] Failed to format snapshot: %s", exc, exc_info=True)
            return ""
