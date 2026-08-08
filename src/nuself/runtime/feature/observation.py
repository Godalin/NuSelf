"""Privacy-safe Tool lifecycle observation effect."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.runtime.event.payload import RuntimeLogEventPayload
from nuself.runtime.feature.effect import (
    BoundFeatureEffect,
    EffectEnvironment,
    FeatureEffect,
    FeatureInvocation,
)


@dataclass(frozen=True)
class ObservationEffect(FeatureEffect):
    """Immutable declaration of safe Tool lifecycle observation."""

    cardinality_key = "projection.observation"

    def bind(self, environment: EffectEnvironment) -> BoundFeatureEffect:
        return _BoundObservationEffect(environment)


class _BoundObservationEffect(BoundFeatureEffect):
    before_priority = 20
    after_priority = 20
    failure_priority = 20

    def __init__(self, environment: EffectEnvironment) -> None:
        self._environment = environment

    def before(self, invocation: FeatureInvocation) -> None:
        self._publish(invocation, "started", None)

    def after(self, invocation: FeatureInvocation, result: object) -> None:
        del result
        self._publish(invocation, "completed", None)

    def failed(self, invocation: FeatureInvocation, error: Exception) -> None:
        self._publish(invocation, "failed", error)

    def _publish(
        self,
        invocation: FeatureInvocation,
        outcome: str,
        error: Exception | None,
    ) -> None:
        events = self._environment.events
        if events is None:
            return
        try:
            events.publish(
                producer=self._environment.producer,
                name="tool.activity",
                payload=RuntimeLogEventPayload(
                    message=f"Tool {outcome}: {invocation.operation}",
                    level="error" if error is not None else "info",
                    status=outcome,
                    metadata={
                        "service_component": invocation.component,
                        "operation": invocation.operation,
                        "execution": invocation.execution,
                        "duration_ms": invocation.duration_ms,
                        **(
                            {"error_type": type(error).__name__}
                            if error is not None
                            else {}
                        ),
                    },
                ).to_mapping(),
            )
        except Exception:
            return
