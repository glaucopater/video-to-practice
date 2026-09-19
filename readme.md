# Video to Practice

Analyze video frames with a local Ollama vision model and generate structured descriptions of movement, posture, and Tai Chi practice.

The project requires FFmpeg to extract video frames, then uses Python and Ollama to analyze selected JPEG or PNG frames.

## Workflow

```text
video file
    ↓ FFmpeg
extracted frames
    ↓ Python + Ollama vision model
JSONL posture and movement descriptions
```

## Features

- Extract video frames with FFmpeg.
- Analyze JPEG or PNG frame sequences with Ollama vision models.
- Sample every Nth frame with `--every`.
- Calculate source-video timestamps with `--fps`.
- Include frame number, video time, model, and response timestamp in output.
- Resume interrupted analyses with `--resume`.
- Retry transient failures and malformed model responses.
- Handle Qwen3-VL responses where valid JSON is returned in `message.thinking` instead of `message.content`.
- Validate analysis fields before writing results.
- Keep failed frames available for later retry.
- Run locally through Ollama.

## Requirements

- Python 3.10 or newer.
- FFmpeg, including `ffmpeg` and `ffprobe`.
- Ollama.
- A vision-capable Ollama model.
- An input video file.
- `requests` Python package.

### Verify the tools

```powershell
ffmpeg -version
ffprobe -version
ollama --version
python --version
```

Install the Python dependency inside the project virtual environment:

```powershell
python -m pip install requests
```

## Project structure

```text
video-to-practice/
├── src/
│   └── analyze_frames.py
├── yt/
│   ├── video.mp4
│   └── frames-jpeg/
├── descriptions.jsonl
├── requirements.txt
└── README.md
```

## Ollama setup

Install Ollama and pull a vision model. The examples use Qwen3-VL 2B:

```powershell
ollama pull qwen3-vl:2b
```

Verify that Ollama is running:

```powershell
ollama list
```

Check loaded models and GPU allocation:

```powershell
ollama ps
```

For single-image analysis, an 8192-token context is generally sufficient. Set it in PowerShell before starting Ollama:

```powershell
$env:OLLAMA_CONTEXT_LENGTH = "8192"
ollama serve
```

A newly loaded model should ideally show `100% GPU` in `ollama ps` when sufficient VRAM is available.

## Extract frames with FFmpeg

FFmpeg is mandatory because the analyzer processes extracted image frames rather than the video file directly.

Create the frame directory:

```powershell
New-Item -ItemType Directory -Force .\yt\frames-jpeg | Out-Null
```

Inspect the input video:

```powershell
ffprobe -v error -select_streams v:0 -show_entries stream=duration,avg_frame_rate,nb_frames -of default=noprint_wrappers=1 .\yt\video.mp4
```

Extract JPEG frames:

```powershell
ffmpeg -i .\yt\video.mp4 -fps_mode passthrough -q:v 3 .\yt\frames-jpeg\frame_%06d.jpg
```

The resulting directory should contain files like:

```text
frames-jpeg/
├── frame_000001.jpg
├── frame_000002.jpg
├── frame_000003.jpg
└── ...
```

For lossless PNG frames instead:

```powershell
New-Item -ItemType Directory -Force .\yt\frames-png | Out-Null
ffmpeg -i .\yt\video.mp4 -fps_mode passthrough .\yt\frames-png\frame_%06d.png
```

## Analyze sampled frames

Analyze every 100th frame from a 30 fps video:

```powershell
python .\src\analyze_frames.py .\yt\frames-jpeg --every 100 --fps 30 --model qwen3-vl:2b --pattern "*.jpg" --output .\descriptions.jsonl --resume
```

With files named `frame_000001.jpg`, `frame_000101.jpg`, and so on:

- `frame_000001.jpg` corresponds to `0.000` seconds.
- `frame_000101.jpg` corresponds to `3.333` seconds.
- `frame_000201.jpg` corresponds to `6.667` seconds.

The timestamp is calculated from the original frame number, not the position in the sampled list.

## Analyze every frame

```powershell
python .\src\analyze_frames.py .\yt\frames-jpeg --fps 30 --model qwen3-vl:2b --pattern "*.jpg" --output .\descriptions.jsonl --resume
```

The default value of `--every` is `1`, so every matching frame is analyzed.

## Resume an analysis

Use `--resume` to skip frame names already present in the JSONL output:

```powershell
python .\src\analyze_frames.py .\yt\frames-jpeg --every 100 --fps 30 --model qwen3-vl:2b --pattern "*.jpg" --output .\descriptions.jsonl --resume
```

The script reports the number of frames found, selected, already completed, and remaining. Successful records are skipped; frames that previously failed can be retried on the next run.

## Command-line options

| Option | Default | Description |
|---|---:|---|
| `frames` | required | Directory containing extracted frames. |
| `--output`, `-o` | `descriptions.jsonl` | JSONL output path. |
| `--model`, `-m` | `gemma4:e2b` | Ollama model name. |
| `--endpoint` | `http://localhost:11434/api/chat` | Ollama chat endpoint. |
| `--pattern` | `*.jpg` | Frame filename pattern. |
| `--every` | `1` | Analyze every Nth frame. |
| `--fps` | `30.0` | Source video frame rate. |
| `--timeout` | `600` | HTTP timeout in seconds per attempt. |
| `--resume` | disabled | Skip frames already present in the output. |
| `--retries` | `3` | Total attempts per frame. |
| `--retry-delay` | `1.0` | Seconds between retry attempts. |

## Output format

The output is JSON Lines: one JSON object per line.

Example:

```json
{
  "frame": "frame_000101.jpg",
  "frame_number": 101,
  "time_seconds": 3.333,
  "model": "qwen3-vl:2b",
  "created_at": "2026-09-19T12:33:23.0182966Z",
  "analysis": {
    "summary": "A practitioner stands in a wide stance outdoors.",
    "posture": "Knees slightly bent with the torso upright and arms held forward.",
    "movement": "No movement direction is determinable from this single frame.",
    "limitations": [
      "A single frame does not prove movement direction."
    ]
  }
}
```

The exact analysis fields depend on the schema currently configured in `src/analyze_frames.py`.

## Troubleshooting

### FFmpeg command not found

Install FFmpeg and ensure its `bin` directory is available in the Windows `PATH`. Verify with:

```powershell
ffmpeg -version
ffprobe -version
```

Restart PowerShell after changing `PATH`.

### No frames found

Check that the frame directory exists and that the pattern matches the extracted files:

```powershell
Get-ChildItem .\yt\frames-jpeg\*.jpg | Select-Object -First 5
```

Use `--pattern "*.png"` for PNG frames.

### The script analyzes all frames instead of every 100th frame

Sampling must happen after discovering and sorting the files:

```python
frame_files = sorted(args.frames.glob(args.pattern))
frame_files = frame_files[::args.every]
```

Do not slice the directory path before calling `glob()`.

### Ollama uses too much GPU memory

Check the loaded model:

```powershell
ollama ps
```

If the context is excessively large, stop Ollama, set a smaller context length, and restart it:

```powershell
$env:OLLAMA_CONTEXT_LENGTH = "8192"
```

### A frame returns empty content

The script logs response metadata and retries the request. Some Qwen3-VL/Ollama responses place valid JSON in `message.thinking` while leaving `message.content` empty. The analyzer can parse the fallback only when it contains valid JSON.

### Output records are not in frame order

Resume runs append newly completed records. A frame that succeeds after retries can therefore appear later in the JSONL file even if its frame number is earlier. Sort the JSONL file numerically by frame number after the run if strict ordering is required.

## Development notes

Keep raw video extraction separate from model analysis. This allows sampling, prompts, schemas, and models to change without extracting the video again.

For reproducible analyses, record the source video FPS, sampling interval, model, prompt/schema version, and Ollama context configuration alongside the JSONL output.
