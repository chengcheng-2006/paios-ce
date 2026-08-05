# Local ASR

Local ASR is the first real capability admitted after the Mock-only release.
It is an experimental (EXPERIMENTAL (real-model smoke passed)) local
file-transcription path.

## Scope

Phase 9A supports:

```text
one existing local audio file
→ audio input policy validation
→ SPEECH_TRANSCRIBE_LOCAL capability check
→ optional faster-whisper adapter
→ typed TranscriptionResult
→ metadata-only audit event
```

Status: **EXPERIMENTAL** (real-model smoke passed on Windows, CPU int8
reference mode, `tiny` model). The capability remains disabled by default.

It does not support:

- microphone capture;
- streaming;
- live channels (Feishu / WeChat / voice calls);
- speaker diarization;
- TTS;
- cloud ASR;
- automatic transcript persistence;
- raw audio persistence.

## Installation

The speech dependency is optional. The base package and all existing CLI
commands work without it.

```bash
pip install -e ".[dev,speech]"
```

## Usage

```bash
paios-ce transcribe sample.wav \
  --model tiny \
  --language en \
  --device cpu \
  --compute-type int8
```

By default, model access is `local_files_only`. A model identifier succeeds
only when the model is already cached locally. A local converted model
directory (faster-whisper / CTranslate2 format) can also be supplied as
`--model /path/to/model-dir`.

### Enabling the capability

Speech is disabled by default. Enable it in the private configuration:

```yaml
speech:
  enabled: true
  local_files_only: true
  max_file_size_mb: 100
  max_duration_seconds: 3600
  allowed_extensions: [wav, mp3, m4a, flac, ogg, opus, webm]
  vad_filter: true
  device: cpu
  compute_type: int8
```

No real path, key, token or model cache may enter committed example
configuration.

## CLI options

| Option | Meaning |
| --- | --- |
| `--model MODEL_OR_LOCAL_PATH` | Model identifier or local converted model path |
| `--language LANGUAGE` | Language hint (default: auto-detect) |
| `--device cpu|cuda|auto` | Inference device (default: `cpu`) |
| `--compute-type TYPE` | Compute type (default: `int8`) |
| `--vad-filter` / `--no-vad-filter` | Enable/disable VAD filtering |
| `--word-timestamps` | Request word-level timestamps |
| `--format json|text` | Output format (default: `json`) |
| `--output FILE` | Write output to a file |
| `--public-config FILE` / `--private-config FILE` | Configuration files |

Stable structured error codes:

```text
E_SPEECH_DISABLED
E_SPEECH_DEPENDENCY_MISSING
E_SPEECH_MODEL_NOT_AVAILABLE_OFFLINE
E_AUDIO_FILE_NOT_FOUND
E_AUDIO_TYPE_NOT_ALLOWED
E_AUDIO_TOO_LARGE
E_AUDIO_DURATION_LIMIT
E_AUDIO_DECODE_FAILED
E_TRANSCRIPTION_FAILED
```

## Privacy defaults

- audio is read in place and opened read-only;
- audio is not copied into the repository;
- audio is not retained by PAIOS CE;
- transcript text is returned to the requesting user only and is not written
  to AuditEvent;
- absolute source paths are redacted (only the basename is exposed);
- model-cache absolute paths never appear in audit or error output;
- model weights and caches are ignored by Git;
- network download is not implicit (`local_files_only = true`).

## Output

JSON output includes:

```text
status
text
language
language_probability
duration_seconds
duration_after_vad_seconds
segments
model
device
compute_type
safe_source_label
```

Audit metadata includes counts and safe labels, never transcript content.

## CPU reference mode

The release-gated reference path is:

```text
device = cpu
compute_type = int8
local_files_only = true
```

CUDA may be tested as supplementary behavior but is not required for Phase 9A
acceptance.

## Model licensing

No model weights are bundled. Users are responsible for reviewing the license
and terms of the model they select.
