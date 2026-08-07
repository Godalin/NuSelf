"""Lifecycle execution of bound feature effects."""

from __future__ import annotations

from collections.abc import Callable

from nuself.runtime.feature.effect import (
    EffectEnvironment,
    FeatureAuditSink,
    FeatureEventPublisher,
    FeatureInvocation,
)
from nuself.runtime.feature.policy import feature_spec
from nuself.runtime.feature.protocol import (
    RejectUnavailableEffectPort,
    ToolEffectPort,
)


class FeatureExecutor:
    """Bind declarations and invoke a feature exactly once."""

    def __init__(
        self,
        *,
        producer: str = "runtime",
        effects: ToolEffectPort | None = None,
        events: FeatureEventPublisher | None = None,
        audits: FeatureAuditSink | None = None,
    ) -> None:
        self._environment = EffectEnvironment(
            producer=producer,
            effect_port=effects or RejectUnavailableEffectPort(),
            events=events,
            audits=audits,
        )

    def invoke[**P, R](
        self,
        function: Callable[P, R],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        spec = feature_spec(function)
        invocation = FeatureInvocation.from_call(
            function,
            component=spec.component,
            operation=(
                spec.tool.name
                if spec.tool is not None and spec.tool.name is not None
                else None
            ),
            execution=spec.execution,
            args=args,
            kwargs=kwargs,
        )
        bound = tuple(
            declaration.bind(self._environment)
            for declaration in spec.effects
        )
        before = sorted(bound, key=lambda effect: effect.before_priority)
        after = sorted(
            bound,
            key=lambda effect: effect.after_priority,
        )
        failed = sorted(
            bound,
            key=lambda effect: effect.failure_priority,
        )
        for effect in before:
            effect.before(invocation)
        try:
            result = function(*args, **kwargs)
        except Exception as error:
            for effect in failed:
                effect.failed(invocation, error)
            raise
        for effect in after:
            effect.after(invocation, result)
        return result


__all__ = ["FeatureExecutor"]
