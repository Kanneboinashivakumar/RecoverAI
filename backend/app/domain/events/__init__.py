# Domain events package
from app.domain.events.schema import NormalizedRevenueEvent
from app.domain.events.normalizer import normalize_event
from app.domain.events.processor import process_revenue_event, EventProcessingResult

__all__ = [
    "NormalizedRevenueEvent",
    "normalize_event",
    "process_revenue_event",
    "EventProcessingResult",
]
