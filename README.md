# Podcast-Generator


A desktop application that transforms Wikipedia articles, PDFs, or plain text into dynamic, AI-narrated podcasts using multiple speakers. Features a PySide6 GUI and supports Google, ElevenLabs, OpenAI, and local voice synthesis (pyttsx3).

---

## Features

- Convert Wikipedia, PDF, or TXT content into podcast audio
- AI-generated dialogue with speaker variation using Gemini
- Multispeaker support: Bonnie, Clyde, Alice, and Bob
- Background music
- Text-to-Speech providers:
  - Google Cloud Text-to-Speech
  - ElevenLabs API
  - OpenAI TTS (`gpt-4o-mini-tts`)
  - pyttsx3 (offline)
- Desktop GUI (PySide6) with:
  - File selection
  - Source type toggles
  - Voice and speaker configuration
  - Progress bar, logging, and playback

---

## Requirements

- Python 3.8+
- FFmpeg installed and added to system PATH
  - [Download FFmpeg](https://ffmpeg.org/download.html)
- Needed:
  - [Google Gemini API](https://makersuite.google.com/app/apikey)

- API Voice Keys:
  - [Google Cloud TTS](https://developers.google.com/workspace/guides/create-credentials)
  - [ElevenLabs API](https://www.elevenlabs.io/api)
  - [OpenAI API](https://platform.openai.com/account/api-keys)
  Music:
  - [JAMENDO]

---

## Installation

git clone https://github.com/Markofbear/Podcast-Generator.git
cd Podcast-Generator
python -m venv venv
source venv/Scripts/activate  # On Windows
pip install -r requirements.txt


Environment Variables

Rename ENV_EXAMPLE.env to .env and fill in your API credentials:

GOOGLE_API_KEY=your-gemini-api-key
GOOGLE_APPLICATION_CREDENTIALS=./gcp-credentials.json
ELEVENLABS_API_KEY=your-elevenlabs-api-key
OPENAI_API_KEY=your-openai-api-key
JAMENDO_CLIENT_ID = XXX-XXX-XXX

These are used only when selecting Google, ElevenLabs, or OpenAI as voice providers.

## Environment & Execution

.env file (rename from ENV_EXAMPLE.env)
GOOGLE_API_KEY: your-gemini-api-key
GOOGLE_APPLICATION_CREDENTIALS: ./gcp-credentials.json
ELEVENLABS_API_KEY: your-elevenlabs-api-key
OPENAI_API_KEY: your-openai-api-key

If you use pyttsx3 (the demo version), You still need Gemini API.


# Launching the application
command: python main.py

