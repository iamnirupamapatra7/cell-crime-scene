"""Gemini as lead investigator: reads measurements + images, picks the next allowlisted tool, writes the report."""
import json

from agents.schemas import DECISION_SCHEMA, REPORT_SCHEMA, Decision, Report

SYSTEM_PROMPT = """You are the lead investigator in Cell Crime Scene, a research quality-control tool for
fluorescence-microscopy nucleus segmentation. It is NOT a diagnostic or clinical tool.

Each turn you receive JSON measurements produced by Python tools, the microscopy image, and an overlay of
the current segmentation (each nucleus a colour; red boxes mark suspicious regions). Choose exactly ONE action:
- a repair tool from `tools` with parameters inside the stated bounds,
- "accept": finalise the best attempt that passed independent verification and send it for human review,
- "abstain": stop and flag the case as unresolved.

Rules:
- Verification is computed independently by Python. You cannot declare success yourself; "accept" is refused
  unless an attempt has passed. Never claim an improvement the metrics do not show.
- Read the verification feedback. merged_objects > 0 means nuclei are still merged (split more: lower
  min_distance, try the other landscape, or erosion_split). Rising split_objects or a positive count_error means
  over-splitting (raise min_distance / lower radius).
- Prefer target="suspicious" so correct nuclei are left untouched. Use base="best" to refine the best attempt.
- Abstain rather than guess when evidence is weak or the budget is nearly spent with no passing attempt.
- Be concise and evidence-linked: cite region labels, areas, solidity and metric values."""


class GeminiPlanner:
    name = "gemini"

    def __init__(self, api_key: str, model: str, thinking_level: str, timeout_s: float = 120):
        from google import genai

        # A call slower than timeout_s fails, and the investigator falls back to the heuristic for that step.
        self.client = genai.Client(api_key=api_key, http_options={"timeout": int(timeout_s * 1000)})
        self.timeout_s = timeout_s
        self.model = model
        self.thinking_level = thinking_level
        self.previous_id = None
        self.api = "interactions"  # drops to "generate_content" if the Interactions API is unavailable

    def _interact(self, text, images, schema):
        """Interactions API (recommended for Argon). Chained with previous_interaction_id so the
        investigation keeps server-side state across turns."""
        import base64

        content = [{"type": "text", "text": text}]
        for caption, png in images:
            content.append({"type": "text", "text": caption})
            content.append({"type": "image", "mime_type": "image/png", "data": base64.b64encode(png).decode()})
        body = dict(model=self.model, system_instruction=SYSTEM_PROMPT, input=content,
                    generation_config={"thinking_level": self.thinking_level},
                    response_format={"type": "text", "mime_type": "application/json", "schema": schema})
        if self.previous_id:
            body["previous_interaction_id"] = self.previous_id
        resp = self.client.interactions.create(**body, timeout=self.timeout_s)
        self.previous_id = getattr(resp, "id", None) or self.previous_id
        return json.loads(resp.output_text)

    def _generate(self, parts, schema):
        from google.genai import types

        base = dict(system_instruction=SYSTEM_PROMPT, response_mime_type="application/json",
                    response_schema=schema)
        try:
            config = types.GenerateContentConfig(
                **base, thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level))
        except Exception:  # older SDK without thinking_level
            config = types.GenerateContentConfig(**base)
        try:
            resp = self.client.models.generate_content(model=self.model, contents=parts, config=config)
        except Exception as exc:
            if "thinking" not in str(exc).lower():
                raise
            resp = self.client.models.generate_content(
                model=self.model, contents=parts, config=types.GenerateContentConfig(**base))
        return json.loads(resp.text)

    def _parts(self, text, images):
        from google.genai import types

        parts = [types.Part.from_text(text=text)]
        for caption, png in images:
            parts.append(types.Part.from_text(text=caption))
            parts.append(types.Part.from_bytes(data=png, mime_type="image/png"))
        return parts

    def _call(self, text, images, schema):
        if self.api == "interactions":
            try:
                return self._interact(text, images, schema)
            except Exception as exc:
                if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                    raise  # quota is per key; the other endpoint would fail the same way
                self.api = "generate_content"
        return self._generate(self._parts(text, images), schema)

    def decide(self, state: dict, images: list[tuple[str, bytes]]) -> Decision:
        text = "Investigation state:\n" + json.dumps(state, indent=1, default=str) + \
               "\n\nDecide the next action."
        return Decision.model_validate(self._call(text, images, DECISION_SCHEMA))

    def write_report(self, final_state: dict) -> Report:
        text = ("Write the final investigation report for the researcher from this record. Report only what "
                "the measurements show; list remaining uncertainties honestly.\n"
                + json.dumps(final_state, indent=1, default=str))
        return Report.model_validate(self._call(text, [], REPORT_SCHEMA))
