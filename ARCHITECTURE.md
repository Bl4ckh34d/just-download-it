# JustDownloadIt - Architecture Overview

## Introduction
JustDownloadIt is a modern, responsive desktop application for downloading media content, with a primary focus on YouTube videos. The application is built using Python with a modern GUI framework (CustomTkinter) and follows a modular architecture pattern for maintainability and extensibility.

## Core Components

### 1. Main Application (`main.py`)
- Entry point of the application
- Initializes the logging system
- Sets up the GUI theme and launches the main window
- Handles global exception management

### 2. Downloader Module (`downloader/`)
#### YouTube Downloader (`youtube_downloader.py`)
- Core downloading functionality using `yt-dlp`
- Supports various video qualities (144p to 4K)
- Handles both video and audio downloads
- Features:
  - Playlist URL extraction
  - Format selection
  - Progress monitoring
  - FFmpeg-based media muxing
  - Filename sanitization

### 3. User Interface (`ui/`)
#### Main Window (`main_window.py`)
- Primary user interface container
- Manages:
  - URL input handling
  - Download progress visualization
  - Settings panel integration
  - Queue management
  - Real-time status updates

#### Settings Panel
- Configuration management
- Quality selection options
- Download path settings

#### Download Widget
- Individual download progress tracking
- Status visualization
- Cancel operation support

### 4. Utilities (`utils/`)
- Logging system
- Exception handling
- File system operations
- URL validation and processing

## Design Principles

1. **Modularity**
   - Clear separation of concerns between UI, download logic, and utilities
   - Each component is self-contained and independently maintainable

2. **Responsiveness**
   - Asynchronous download operations
   - Multi-process architecture for handling concurrent downloads
   - Non-blocking UI updates

3. **Reliability**
   - Comprehensive error handling
   - Robust logging system
   - Recovery mechanisms for failed downloads

4. **User Experience**
   - Clean, modern dark-themed interface
   - Real-time progress updates
   - Intuitive controls and feedback

## Process Flow
1. User inputs URL(s)
2. Application validates input
3. Download manager initializes appropriate downloader
4. Progress is monitored and displayed in real-time
5. Downloaded files are processed and saved to specified location

## Dependencies
- `customtkinter`: Modern UI framework
- `yt-dlp`: Core download functionality
- `FFmpeg`: Media processing
- Additional Python standard libraries

## Note
This architecture document should be updated whenever significant changes are made to the codebase. Last updated: 2025-01-19

## Future Considerations
- Plugin system for additional download sources
- Enhanced media format support
- Advanced queue management features
- Custom theming support
