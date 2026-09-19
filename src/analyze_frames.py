#!/usr/bin/env python3

import argparse
import base64
import json
import sys
import time
from pathlib import Path

import requests


SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "posture": {"type": "string"},
        "movement": {"type": "string"},
        "limitations": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "summary",
        "posture",
        "movement",
        "limitations",
    ],
}


PROMPT = (
    "Return one compact JSON object immediately. "
    "Do not think aloud or explain your reasoning. "
    "Use exactly these keys: summary, posture, movement, limitations. "
    "Describe only visible facts in this single image. "
    "Describe the person's stance, legs, torso, arms, hands, and gaze "
    "briefly. Describe movement only if visible from posture or blur. "
    "Do not infer movement direction from one frame. "
    "Do not identify a named Tai Chi posture unless clearly visible. "
    "If something cannot be determined, write that in limitations. "
    "Do not repeat observations. Return no Markdown or text outside JSON."
)


def validate_result(result):
    if not isinstance(result, dict):
        raise ValueError("Model output is not a JSON object")

    required_keys = {
        "summary",
        "posture",
        "movement",
        "limitations",
    }
    missing = required_keys - set(result)

    if missing:
        raise ValueError(
            f"JSON is missing required keys: {sorted(missing)}"
        )

    return result


def request_analysis(payload, args):
    last_error = None

    for attempt in range(1, args.retries + 1):
        try:
            response = requests.post(
                args.endpoint,
                json=payload,
                timeout=args.timeout,
            )
            response.raise_for_status()

            response_data = response.json()
            content = response_data.get(
                "message", {}
            ).get(
                "content", ""
            ).strip()

            message = response_data.get("message", {})
            content = message.get("content", "").strip()
            thinking = message.get("thinking", "").strip()

            if not content and thinking:
                candidate = thinking

                if candidate.startswith("<think>"):
                    candidate = candidate[len("<think>"):].strip()

                if candidate.endswith("</think>"):
                    candidate = candidate[:-len("</think>")].strip()
            else:
                candidate = content

            if not candidate:
                raise ValueError(
                    "Ollama returned neither content nor thinking. "
                    f"response={json.dumps(response_data, ensure_ascii=False)[:2000]}"
                )

            try:
                result = validate_result(json.loads(candidate))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Ollama returned non-JSON content: {content[:1000]!r}"
                ) from error

            return response_data, result

        except (
            requests.RequestException,
            json.JSONDecodeError,
            ValueError,
        ) as error:
            last_error = error

            if attempt < args.retries:
                print(
                    f"Retry {attempt}/{args.retries - 1} after error: {error}",
                    file=sys.stderr,
                )
                time.sleep(args.retry_delay)

    raise RuntimeError(
        f"Analysis failed after {args.retries} attempts: {last_error}"
    )


def analyze_frame(image_path, args):
    image_data = base64.b64encode(
        image_path.read_bytes()
    ).decode("ascii")

    payload = {
        "model": args.model,
        "think": False,
        "messages": [
            {
                "role": "user",
                "content": PROMPT,
                "images": [image_data],
            }
        ],
        "stream": False,
        "format": SCHEMA,
        "options": {
            "temperature": 0,
            "num_predict": 300,
        },
    }

    response_data, result = request_analysis(payload, args)

    return {
        "model": response_data.get("model", args.model),
        "created_at": response_data.get("created_at"),
        "analysis": result,
    }


def load_completed_frames(output_path):
    completed = set()

    if not output_path.exists():
        return completed

    with output_path.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                record = json.loads(line)
                frame = record.get("frame")
                if frame:
                    completed.add(frame)
            except json.JSONDecodeError:
                continue

    return completed


def frame_number_from_path(image_path):
    try:
        return int(image_path.stem.rsplit("_", 1)[1])
    except (IndexError, ValueError) as error:
        raise ValueError(
            f"Cannot extract frame number from filename: {image_path.name}"
        ) from error


def sort_output_file(output_path):
    records = []

    if not output_path.exists():
        return

    with output_path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line:
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                print(
                    f"Warning: ignoring invalid JSON line: {line[:100]}",
                    file=sys.stderr,
                )

    records.sort(
        key=lambda record: int(
            record["frame"].rsplit("_", 1)[1].rsplit(".", 1)[0]
        )
    )

    with output_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

def main():
    parser = argparse.ArgumentParser(
        description="Analyze image frames with an Ollama vision model."
    )

    parser.add_argument(
        "frames",
        type=Path,
        help="Directory containing the extracted frames",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("descriptions.jsonl"),
        help="Output JSONL file",
    )
    parser.add_argument(
        "-m",
        "--model",
        default="gemma4:e2b",
        help="Ollama model name",
    )
    parser.add_argument(
        "--endpoint",
        default="http://localhost:11434/api/chat",
        help="Ollama API endpoint",
    )
    parser.add_argument(
        "--pattern",
        default="*.jpg",
        help="Frame filename pattern, for example '*.jpg' or '*.png'",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="HTTP timeout in seconds per attempt",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip frames already present in the output file",
    )
    parser.add_argument(
        "--every",
        type=int,
        default=1,
        help="Analyze every Nth frame (default: 1 = all frames)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=30.0,
        help="Source video frame rate",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Total attempts per frame, including the first attempt",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=1.0,
        help="Seconds to wait between retries",
    )

    args = parser.parse_args()

    if not args.frames.exists():
        raise SystemExit(f"Frame directory does not exist: {args.frames}")
    if not args.frames.is_dir():
        raise SystemExit(f"Frames path is not a directory: {args.frames}")
    if args.every < 1:
        raise SystemExit("--every must be >= 1")
    if args.fps <= 0:
        raise SystemExit("--fps must be greater than 0")
    if args.retries < 1:
        raise SystemExit("--retries must be >= 1")
    if args.retry_delay < 0:
        raise SystemExit("--retry-delay must be >= 0")

    all_frame_files = sorted(args.frames.glob(args.pattern))

    if not all_frame_files:
        raise SystemExit(
            f"No frames matching {args.pattern!r} found in {args.frames}"
        )

    frame_files = all_frame_files[::args.every]
    completed = load_completed_frames(args.output) if args.resume else set()
    pending = [path for path in frame_files if path.name not in completed]

    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Found frames: {len(all_frame_files)}", file=sys.stderr)
    print(f"Selected frames: {len(frame_files)}", file=sys.stderr)
    print(
        f"Already completed: {len(frame_files) - len(pending)}",
        file=sys.stderr,
    )
    print(f"Remaining: {len(pending)}", file=sys.stderr)

    if not pending:
        print("Nothing to analyze.", file=sys.stderr)
        return

    with args.output.open("a", encoding="utf-8") as output_file:
        for index, image_path in enumerate(frame_files, start=1):
            if image_path.name in completed:
                print(
                    f"[{index}/{len(frame_files)}] Skipping {image_path.name}",
                    file=sys.stderr,
                )
                continue

            started = time.time()

            try:
                result = analyze_frame(image_path, args)
                frame_number = frame_number_from_path(image_path)

                record = {
                    "frame": image_path.name,
                    "frame_number": frame_number,
                    "time_seconds": round(
                        (frame_number - 1) / args.fps,
                        3,
                    ),
                    **result,
                }

                output_file.write(
                    json.dumps(record, ensure_ascii=False) + "\n"
                )
                output_file.flush()
                completed.add(image_path.name)

                elapsed = time.time() - started
                print(
                    f"[{index}/{len(frame_files)}] "
                    f"{image_path.name} ({elapsed:.1f}s)",
                    file=sys.stderr,
                )

            except Exception as error:
                print(
                    f"ERROR processing {image_path.name}: {error}",
                    file=sys.stderr,
                )

    sort_output_file(args.output)


if __name__ == "__main__":
    main()
