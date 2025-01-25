# JustDownloadIt

A multi-threaded file downloader with YouTube support, built with Python.

<p align="center">
  <img src="https://github.com/Bl4ckh34d/just-download-it/blob/main/assets/GUI.png" width="500" alt="GUI">
</p>
## Features
- Multi-threaded file downloads
- YouTube video downloads with separate video/audio processing
- Process-safe architecture
- Modern and responsive UI
- Progress tracking with speed and size information

## Requirements
- Python 3.8+
- ffmpeg (for YouTube video processing)

## Installation
1. Install the required Python packages:
```bash
pip install -r requirements.txt
```

2. Install ffmpeg:
   - Windows: Download from https://ffmpeg.org/download.html
   - Make sure ffmpeg is in your system PATH

## Usage
Run the application:
```bash
python main.py
```

## Architecture
The application is split into two main components:
1. Core downloading engine (process-safe and thread-safe)
2. UI interface (responsive and non-blocking)

Each download runs in its own process to ensure stability and responsiveness.
