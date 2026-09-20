# Backend Service: tts

This module owns text-to-speech validation, segmentation, streaming, provider
pipeline orchestration, and usage recording.

Entry files in this directory: `__init__.py`, `pipeline.py`,
`streaming_tts.py`, `validation.py`, `tts_usage_recorder.py`.

## Do

- Validate TTS settings strictly before provider calls so malformed requests
  fail early and predictably.
- Preserve the boundary and stripping helpers that keep partial markdown, XML,
  or media fragments from breaking streams.
- Record TTS usage through the shared recorder path so metering stays
  consistent with generated audio behavior.

## Avoid

- Do not fork request validation or segmentation logic into multiple entry
  points where behavior can drift.
- Do not change streaming chunk semantics without checking both the runtime
  pipeline and usage-recorder expectations.
- Do not skip metering updates when new TTS paths or providers are introduced
  in the pipeline.

## Tests

`cd src/api && pytest tests/service/tts/ -q`
