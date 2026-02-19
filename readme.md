# Fulloch

<p align="center">
  <img src="fulloch.png" alt="Fulloch Logo" width="200">
</p>

> The **Ful**ly **Loc**al **H**ome Voice Assistant

A privacy-focused voice assistant that runs speech recognition, text-to-speech, and language model inference entirely on-device with no cloud dependencies.

## Features

- **100% Local Processing**: All AI runs on your hardware
- **Privacy First**: No data leaves your device for AI processing
- **Low Latency**: Optimized for real-time voice interaction
- **Extensible**: Easy to add new smart home integrations

## Videos

#### AI and Voice Latency on NVIDIA GeForce RTX 5060 Ti 16 GB

Example video showing response times of the full Qwen3 pipeline with voice cloning using a Morgan Freeman recording. In this example the SearXNG server is not running so it shows the model reverting to its own knowledge when unable to obtain web search information.


https://github.com/user-attachments/assets/44e5fe84-bfa0-4463-9818-538676f3ba1c


#### Intent and Home Automation Latency on NVIDIA GeForce RTX 5060 Ti 16 GB

Example video showing response times for turning on Philips Hue lights and playing music through Spotify. Old mobile phone running AudioRelay is used as remote microphone and speaker.


https://github.com/user-attachments/assets/b06fe935-c5bf-4b50-a931-7799cb787801


## Architecture

```
                           +-------------------------+
                           | Home Assistant / Client |
                           +------------+------------+
                                        |
                           +------------v------------+
                           | OpenAI-Compatible API   |
                           |  /v1/chat/completions   |
                           |  /v1/audio/transcriptions|
                           |  /v1/audio/speech       |
                           +------------+------------+
                                        |
                    +-------------------+-------------------+
                    |                                       |
           +--------v---------+                    +--------v---------+
           |   Regex Intent   |                    |    Qwen 3 SLM    |
           |   (Fast Path)    |                    | Intent + Chat LLM|
           +--------+---------+                    +--------+---------+
                    |                                       |
                    +-------------------+-------------------+
                                        |
                           +------------v------------+
                           |       Tool Registry     |
                           |  (HA, Spotify, Hue, etc)|
                           +------------+------------+
                                        |
                    +-------------------+-------------------+
                    |                                       |
           +--------v---------+                    +--------v---------+
           | Qwen3/Moonshine  |                    | Qwen3/Kokoro TTS |
           |      ASR         |                    |  (audio output)  |
           +------------------+                    +------------------+
```

## Prerequisites

- Linux-based OS
- Python 3.10+
- CUDA-capable GPU (recommended) or CPU
- ~4GB disk space for models
- Home Assistant (optional, for voice pipeline integration)

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/fulloch.git
cd fulloch
pip install -r requirements.txt
# Install special packages (see requirements.txt for details)
pip install --no-deps git+https://github.com/rekuenkdr/Qwen3-TTS-streaming.git@97da215
# GPU only: pip install --no-build-isolation --no-deps git+https://github.com/Dao-AILab/flash-attention.git@ef9e6a6
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your settings (see Environment Configuration section below).

### 3. Download Models

The launch script handles model downloads automatically:

```bash
./launch.sh
```

Or manually download:
- [Qwen3-4B-Instruct GGUF](https://huggingface.co/Qwen) → `data/models/`
- Qwen3-ASR, Qwen3-TTS, Moonshine Tiny, and Kokoro download automatically on first run

### 4. Run

```bash
python app.py
```

Server defaults to `http://0.0.0.0:8000`.

### 5. API Endpoints

- `POST /v1/chat/completions` (OpenAI-compatible chat)
- `POST /v1/audio/transcriptions` (OpenAI Whisper-compatible STT)
- `POST /v1/audio/speech` (OpenAI TTS-compatible speech)
- `GET /v1/models`
- `GET /health`

## Docker Deployment

```bash
./launch.sh  # Downloads models, configures GPU/CPU, starts services
```

The launch script:
1. Downloads required models if not present
2. Detects GPU availability
3. Starts the API service

## GHCR Deployment

Build and push manually:

```bash
# CPU image
docker build -t ghcr.io/k0walski8/fulloch-hagp:latest .
docker push ghcr.io/k0walski8/fulloch-hagp:latest

# GPU image
docker build -f Dockerfile_gpu -t ghcr.io/k0walski8/fulloch-hagp:gpu-latest .
docker push ghcr.io/k0walski8/fulloch-hagp:gpu-latest
```

## Environment Configuration

### Core Settings

```bash
FULLOCH_USE_AI=true
FULLOCH_USE_TINY_ASR=false
FULLOCH_USE_TINY_TTS=false
FULLOCH_VOICE_CLONE=cori
```

### API Settings

```bash
FULLOCH_HOST=0.0.0.0
FULLOCH_PORT=8000
FULLOCH_API_KEY=
FULLOCH_CHAT_MODEL=fulloch-qwen3-slm
FULLOCH_STT_MODEL=qwen3-asr-1.7b
FULLOCH_TTS_MODEL=qwen3-tts-1.7b
```

**ASR Options:**
- `use_tiny_asr: false` (default) — Uses Qwen3-ASR-1.7B for higher accuracy
- `use_tiny_asr: true` — Uses Moonshine Tiny for low-resource edge devices

**TTS Options:**
- `use_tiny_tts: false` (default) — Uses Qwen3-TTS with voice cloning for natural speech
- `use_tiny_tts: true` — Uses Kokoro TTS for faster synthesis on low-resource edge devices

**Voice Cloning:**
- `voice_clone: "name"` — Specifies which voice to clone for Qwen3 TTS. Place your reference audio (`name.wav`) and transcript (`name.txt`) in `data/voices/`. Only used when `use_tiny_tts: false`.

### Spotify

1. Create an app at [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Add `http://localhost:8888/callback` as redirect URI
3. Configure `.env`:

```bash
ENABLE_SPOTIFY=true
SPOTIPY_CLIENT_ID=your_client_id
SPOTIPY_CLIENT_SECRET=your_client_secret
SPOTIPY_REDIRECT_URI=http://localhost:8888/callback
SPOTIFY_DEVICE_ID=Your Speaker Name
SPOTIFY_USE_AVR=false
```

### Philips Hue

1. Press the button on your Hue Bridge
2. Run the app to auto-register
3. Configure `.env`:

```bash
ENABLE_PHILIPS_HUE=true
PHILIPS_HUE_HUB_IP=192.168.1.100
```

### Google Calendar

1. Create credentials at [Google Cloud Console](https://console.cloud.google.com/)
2. Enable Google Calendar API
3. Download OAuth credentials JSON
4. Configure `.env`:

```bash
ENABLE_GOOGLE_CALENDAR=true
GOOGLE_CREDENTIALS_FILE=./data/credentials.json
GOOGLE_TOKEN_FILE=./data/token.json
```

### BOM Australia Weather

```bash
BOM_DEFAULT_LOCATION=Sydney
```

### Web Search (External SearXNG + Optional OpenRouter)

```bash
SEARCH_SEARXNG_URL=http://192.168.50.153:30053
```

Optional `.env` values for OpenRouter web-answer synthesis:

```bash
OPENROUTER_WEB_SEARCH_ENABLED=true
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=google/gemini-2.0-flash-001
```

### Home Assistant

You can use Fulloch as the backend for Home Assistant Voice via OpenAI-compatible integrations.

1. Run Fulloch and ensure Home Assistant can reach `http://<fulloch-host>:8000`.
2. In Home Assistant, configure OpenAI-compatible providers for:
- Conversation (`/v1/chat/completions`)
- Speech-to-Text (`/v1/audio/transcriptions`)
- Text-to-Speech (`/v1/audio/speech`)
3. Use the model IDs from `FULLOCH_CHAT_MODEL`, `FULLOCH_STT_MODEL`, and `FULLOCH_TTS_MODEL`.
4. If `FULLOCH_API_KEY` is set, use it as Bearer token in Home Assistant.

Fulloch can also call Home Assistant as a tool for device control (env-only):

```bash
ENABLE_HOME_ASSISTANT=true
HOME_ASSISTANT_URL=http://192.168.1.50:8123
HOME_ASSISTANT_TOKEN=your_long_lived_token
HOME_ASSISTANT_ENTITY_ALIASES={\"living room lights\":\"light.living_room\",\"front door\":\"lock.front_door\"}
```

Music Assistant speaker playback compatibility (Home Assistant Music Assistant):

```bash
ENABLE_MUSIC_ASSISTANT=true
MUSIC_ASSISTANT_DEFAULT_PLAYER=media_player.living_room
MUSIC_ASSISTANT_PLAYER_ALIASES={\"kitchen speaker\":\"media_player.kitchen\"}
```

With `ENABLE_MUSIC_ASSISTANT=true`, Fulloch registers `play_song`, `pause`, and `resume` tools that control HA speakers.

**Important**: The Home Assistant integration is **disabled by default**. When enabled, it registers generic tool names like `turn_on`, `turn_off`, and `toggle` which may conflict with other integrations (e.g., Philips Hue lighting tools). Only enable this if you want Home Assistant to be your primary home automation controller.

If you use both Home Assistant and direct integrations (like Philips Hue), keep `ENABLE_HOME_ASSISTANT=false` and use the direct integrations instead.

### Other Integrations

See `.env.example` for all available integration variables:
- LG ThinQ (smart appliances)
- WebOS TV control
- Pioneer/Onkyo AVR
- Airtouch HVAC
- External SearXNG web search

## Example Prompts

- "Play some jazz in Spotify"
- "Turn on the kitchen lights"
- "What is on my calendar today?"
- "What's the weather in Sydney?"
- "Summarize today's top tech news"

## Project Structure

```
fulloch/
├── app.py              # API entry point
├── api/                # OpenAI-compatible HTTP routes
│   └── server.py
├── core/               # Core modules
│   ├── api_service.py  # Shared inference orchestration
│   ├── asr.py          # Qwen3 ASR (default)
│   ├── asr_tiny.py     # Moonshine Tiny ASR (edge devices)
│   ├── tts.py          # Qwen3 TTS with voice cloning (default)
│   ├── tts_tiny.py     # Kokoro TTS (edge devices)
│   ├── slm.py          # Qwen language model
│   └── assistant.py    # Legacy wakeword loop (not default runtime)
├── tools/              # Smart home integrations
│   ├── tool_registry.py
│   ├── spotify.py
│   ├── lighting.py
│   └── ...
├── utils/              # Utilities
│   ├── intent_catch.py # Regex intent matching
│   ├── intents.py      # Intent handler
│   └── system_prompts.py
├── audio/              # Audio utilities
│   └── beep_manager.py
└── data/               # Configuration and models
    └── models/         # Downloaded models
```

## Troubleshooting

### Home Assistant cannot connect

- Check `http://<fulloch-host>:8000/health` from the Home Assistant host
- Verify `api.port` and Docker port mapping
- If `FULLOCH_API_KEY` is set, verify bearer token in Home Assistant settings

### Model loading fails

- Ensure sufficient disk space (~4GB)
- Check CUDA installation if using GPU
- Verify model files are in `data/models/`

### Spotify not working

- Run `python tools/spotify.py` to test authentication
- Verify redirect URI matches in Spotify Dashboard
- Check that Spotify device is active

### High CPU/Memory usage

- Use GPU acceleration if available
- Reduce `N_CONTEXT` in `core/slm.py` for less memory
- Disable SLM by setting `general.use_ai: false`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:
- Adding new tools
- Code style
- Pull request process

## Similar Projects

- [Rhasspy](https://github.com/rhasspy) - Open source voice assistant toolkit
- [Home Assistant](https://github.com/home-assistant) - Full home automation platform
- [OpenVoiceOS](https://github.com/OpenVoiceOS) - Community-driven voice assistant

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.
