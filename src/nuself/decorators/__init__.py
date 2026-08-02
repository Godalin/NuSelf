"""Public spelling for inert, orthogonal feature declarations."""

from nuself.runtime.feature.policy import (
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
