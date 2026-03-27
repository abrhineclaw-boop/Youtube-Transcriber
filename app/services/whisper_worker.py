"""Standalone Whisper transcription worker.

Runs in a subprocess so that torch/whisper memory is fully reclaimed on exit.
Usage: python -m app.services.whisper_worker <audio_path> <model_name>
Outputs JSON segments to stdout.
"""

import json
import os
import sys


def main():
    if len(sys.argv) != 3:
        print("Usage: whisper_worker.py <audio_path> <model_name>", file=sys.stderr)
        sys.exit(1)

    audio_path = sys.argv[1]
    model_name = sys.argv[2]

    try:
        import whisper

        model = whisper.load_model(model_name)

        # Redirect stdout during transcription to suppress Whisper's
        # "Detected language: ..." output which corrupts our JSON.
        real_stdout = sys.stdout
        sys.stdout = open(os.devnull, "w")
        try:
            result = model.transcribe(audio_path, verbose=False)
        finally:
            sys.stdout.close()
            sys.stdout = real_stdout

        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "start": round(seg["start"], 2),
                "end": round(seg["end"], 2),
                "text": seg["text"].strip(),
            })

        json.dump(segments, sys.stdout)
        sys.stdout.flush()

    except Exception as e:
        print(f"Whisper worker error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
