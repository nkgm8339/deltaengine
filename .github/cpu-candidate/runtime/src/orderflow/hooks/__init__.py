"""Independent observational Hook contracts.

Hooks are evidence records, never orders, probabilities, or composite scores.
"""

from .models import (
    CalibrationStatus,
    DirectionHint,
    HookCandidate,
    HookEvent,
    HookQualityStatus,
    HookSide,
    HookThreshold,
)
from .registry import HOOK_REGISTRY, HookDefinition, require_hook
from .dom_features import DomFeatureCache, DomFeatureDelta, DomFeatures
from .dom_iceberg import DomIcebergDetector
from .dom_liquidity import DomLiquidityDetector
from .dom_quote_motion import DomQuoteMotionDetector
from .dom_wall import DomWallDetector
from .flow_transition import FlowTransitionDetector
from .interaction import InteractionDetector
from .liquidation import LiquidationDetector
from .open_interest import OpenInterestDetector
from .price_structure import PriceStructureDetector

__all__ = [
    "CalibrationStatus",
    "DirectionHint",
    "HOOK_REGISTRY",
    "HookCandidate",
    "HookDefinition",
    "HookEvent",
    "HookQualityStatus",
    "HookSide",
    "HookThreshold",
    "DomFeatureCache",
    "DomFeatureDelta",
    "DomFeatures",
    "DomIcebergDetector",
    "DomLiquidityDetector",
    "DomQuoteMotionDetector",
    "DomWallDetector",
    "FlowTransitionDetector",
    "InteractionDetector",
    "LiquidationDetector",
    "OpenInterestDetector",
    "PriceStructureDetector",
    "require_hook",
]
