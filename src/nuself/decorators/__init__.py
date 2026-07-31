"""Public spelling for inert, orthogonal feature declarations."""

from .approval import approval_required
from nuself.runtime.features import (
    AuditPolicy,
    ConfirmationPolicy,
    FeaturePolicyConflictError,
    FeatureSpec,
    ObservationPolicy,
    audited,
    component,
    feature_spec,
    mutating,
    observed,
    readonly,
    requires_confirmation,
    tool,
)

__all__ = [
    "AuditPolicy",
    "ConfirmationPolicy",
    "FeaturePolicyConflictError",
    "FeatureSpec",
    "ObservationPolicy",
    "audited",
    "component",
    "feature_spec",
    "mutating",
    "observed",
    "readonly",
    "requires_confirmation",
    "tool",
]
