"""Stable domain audit projection effect."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.runtime.feature.effect import (
    BoundFeatureEffect,
    EffectEnvironment,
    FeatureAuditRecord,
    FeatureEffect,
    FeatureInvocation,
)


@dataclass(frozen=True)
class AuditEffect(FeatureEffect):
    """Immutable declaration of one success-only domain audit."""

    cardinality_key = "projection.audit"

    event: str

    def __post_init__(self) -> None:
        if not self.event.strip():
            raise ValueError("audit event must not be blank")

    def bind(self, environment: EffectEnvironment) -> BoundFeatureEffect:
        return _BoundAuditEffect(self, environment)


class _BoundAuditEffect(BoundFeatureEffect):
    after_priority = 10

    def __init__(
        self,
        declaration: AuditEffect,
        environment: EffectEnvironment,
    ) -> None:
        self._declaration = declaration
        self._environment = environment

    def after(self, invocation: FeatureInvocation, result: object) -> None:
        del result
        audits = self._environment.audits
        if audits is None:
            return
        audits.project_best_effort(FeatureAuditRecord(
            component=invocation.component,
            event=self._declaration.event,
            operation=invocation.operation,
            outcome="completed",
        ))
