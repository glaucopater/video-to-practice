# Video-to-Practice Commands

## 1. Create the frame directory

```powershell
New-Item -ItemType Directory -Force .\yt\frames-jpeg | Out-Null
```

## 2. Inspect the video

```powershell
ffprobe -v error -select_streams v:0 -show_entries stream=duration,avg_frame_rate,nb_frames -of default=noprint_wrappers=1 .\yt\video.mp4
```

## 3. Extract JPEG frames

```powershell
ffmpeg -i .\yt\video.mp4 -fps_mode passthrough -q:v 3 .\yt\frames-jpeg\frame_%06d.jpg
```

Use PNG instead if lossless frames are required:

```powershell
New-Item -ItemType Directory -Force .\yt\frames-png | Out-Null
ffmpeg -i .\yt\video.mp4 -fps_mode passthrough .\yt\frames-png\frame_%06d.png
```

## 4. Analyze sampled frames

Analyze every 100th frame at 30 fps with Qwen3-VL:

```powershell
python .\src\analyze_frames.py .\yt\frames-jpeg --every 100 --fps 30 --model qwen3-vl:2b --pattern "*.jpg" --output .\descriptions.jsonl --resume
```

The `--resume` option skips frames already present in `descriptions.jsonl` and retries missing frames.

## 5. Analyze every frame

```powershell
python .\src\analyze_frames.py .\yt\frames-jpeg --fps 30 --model qwen3-vl:2b --pattern "*.jpg" --output .\descriptions.jsonl --resume
```

## 6. Use another Ollama model

```powershell
python .\src\analyze_frames.py .\yt\frames-jpeg --fps 30 --model gemma4:e4b --pattern "*.jpg" --output .\descriptions.jsonl --resume
```

Or:

```powershell
python .\src\analyze_frames.py .\yt\frames-jpeg --fps 30 --model llava --pattern "*.jpg" --output .\descriptions.jsonl --resume
```

## 7. Start Ollama

```powershell
ollama serve
```

For Qwen3-VL:

```powershell
ollama pull qwen3-vl:2b
```

Check loaded models and GPU usage:

```powershell
ollama ps
```

## 8. Optional llama.cpp commands

These are alternatives to Ollama, not required for the Python analyzer:

```powershell
llama-server -hf Qwen/Qwen3-VL-2B-Instruct-GGUF
```

Use only one inference server at a time if they bind to the same endpoint or GPU.
