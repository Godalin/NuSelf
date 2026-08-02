"""Public spelling for inert, orthogonal feature declarations."""

from nuself.runtime.feature.policy import (
    AuditPolicy,
    ConfirmationPolicy,
    CompactPolicy,
    FeaturePolicyConflictError,
    FeatureSpec,
    ObservationPolicy,
    audited,
    component,
    compact,
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
    "CompactPolicy",
    "FeaturePolicyConflictError",
    "FeatureSpec",
    "ObservationPolicy",
    "audited",
    "component",
    "compact",
    "feature_spec",
    "mutating",
    "observed",
    "readonly",
    "requires_confirmation",
    "tool",
]
