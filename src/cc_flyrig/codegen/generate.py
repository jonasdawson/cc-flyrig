"""Coordinate one generation run: load -> resolve -> translate -> emit -> render -> write.

``Generator`` is the delegate the ``__main__`` composition root hands off to. It owns no codegen
logic of its own — it wires the stateless collaborators around the loaded IR and the injected
``RuntimeProfile``, and writes the result. ``run()`` is the testable seam (construct with real or
fake collaborators, no argv needed).

This module imports core modules only — no ``..cli``. Concrete tooling (formatters/checkers) is
resolved at the composition root, in ``toolchain.py``, and handed in as ``profile.toolchain``.

The pure transformers ``TypeNodeBuilder``/``Resolver`` are built inside ``run()`` because they depend
on the runtime-loaded IR; everything else is injected.
"""

from dataclasses import dataclass
from pathlib import Path

from .load import IntermediateRepresentationLoader
from .profile import RuntimeProfile
from .render import EntrypointContext, EntrypointRenderer
from .resolve import Resolver
from .settings import Settings
from .translate import TypeNodeBuilder, snake_case


@dataclass(frozen=True, slots=True)
class Generator:
    """Wires the pipeline around the loaded IR and writes the typed entrypoint."""

    settings: Settings
    profile: RuntimeProfile
    loader: IntermediateRepresentationLoader
    renderer: EntrypointRenderer

    def run(self) -> Path:
        """Generate the entrypoint for ``settings.event`` and write it; return the path written."""
        ir = self.loader.load()
        profile = self.profile
        event = self.settings.event
        input_name = f"{event}Input"
        output_name = f"{event}Output"
        if input_name not in ir.defs:
            raise ValueError(f"unknown event {event!r}: no {input_name} in cc-{ir.cc_version}")

        has_output = output_name in ir.defs
        roots = [input_name, output_name] if has_output else [input_name]
        specs = Resolver(ir, TypeNodeBuilder(ir, profile), profile).resolve(roots)
        if has_output:
            output_class = profile.class_name(output_name)
            decision_pattern = ir.defs[output_name].get("x-decision-pattern", "")
        else:
            output_class = None
            decision_pattern = ir.defs[input_name].get("x-decision-pattern", "")
        ctx = EntrypointContext(
            cc_version=ir.cc_version,
            schema_date=ir.schema_date,
            event=event,
            event_snake=snake_case(event),
            input_class=profile.class_name(input_name),
            output_class=output_class,
            decision_pattern=decision_pattern,
            runtime=profile.runtime,
            specs=specs,
        )

        fmt = profile.toolchain.format
        check = profile.toolchain.check
        harness_text = fmt(self.renderer.render_harness(ctx))
        stub_text = fmt(self.renderer.render_stub(ctx))
        check(harness_text)
        check(stub_text)

        event_dir = self.settings.out_dir / snake_case(event)
        event_dir.mkdir(parents=True, exist_ok=True)
        (event_dir / f"_harness.{profile.extension}").write_text(harness_text)
        (event_dir / f"{profile.stub_name}.{profile.extension}").write_text(stub_text)
        return event_dir
