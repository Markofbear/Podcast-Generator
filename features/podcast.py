import os
import glob
import fitz
import pyttsx3
import requests
import wikipediaapi
from datetime import datetime
from urllib.parse import unquote
from pydub import AudioSegment
from dotenv import load_dotenv
import google.generativeai as genai
from google.cloud import texttospeech
from elevenlabs.client import ElevenLabs
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import re
import openai

load_dotenv()


class PodcastGenerator:
    def __init__(self, provider="pyttsx3", log_func=print, manuscript_creator="OpenAI GPT-4"):
        self.provider = provider
        self.log = log_func
        self.manuscript_creator = manuscript_creator

        os.makedirs("podcast/chunks", exist_ok=True)
        os.makedirs("podcast", exist_ok=True)

        self.voice_map = {
            "Bonnie": {"google": "en-US-Wavenet-C", "elevenlabs": "lxYfHSkYm1EzQzGhdbfc", "pyttsx3": "Zira", "openai": "nova"},
            "Clyde": {"google": "en-US-Wavenet-D", "elevenlabs": "pVnrL6sighQX7hVz89cp", "pyttsx3": "David", "openai": "fable"},
            "Alice": {"google": "en-US-Wavenet-F", "elevenlabs": "aEO01A4wXwd1O8GPgGlF", "pyttsx3": "Hazel", "openai": "shimmer"},
            "Bob": {"google": "en-US-Wavenet-B", "elevenlabs": "UgBBYS2sOqTuMpoF3BR0", "pyttsx3": "David", "openai": "onyx"},
        }

        self.gcp_client = texttospeech.TextToSpeechClient() if provider == "google" else None
        self.eleven_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY")) if provider == "elevenlabs" else None
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
            raise RuntimeError("OPENAI_API_KEY not set in environment")

    def summarize_and_format_dialogue(self, text, speakers, target_length):
        if not text.strip():
            raise RuntimeError("Input text is empty. Cannot generate dialogues.")

        word_count_map = {
            "Short (5 min)": 700,
            "Medium (10 min)": 1500,
            "Long (20 min)": 3000,
        }
        target_words = word_count_map.get(target_length, 1000)
        speaker_list = ", ".join(speakers)

        base_prompt = f"""
Convert the following article into a detailed, engaging dialogue between {speaker_list}.
- Target ~{target_words} words
- Natural back-and-forth conversation
- Include questions, clarifications, and debates
- Output only in format: SpeakerName: line

Article:
{text}
"""

       
        if self.manuscript_creator == "OpenAI GPT-4":
            resp = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": base_prompt}],
                temperature=0.7,
                max_tokens=4000,
            )
            dialogue_text = resp.choices[0].message.content

        elif self.manuscript_creator == "Gemini 2.0":
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(base_prompt)
            dialogue_text = response.text 


        elif self.manuscript_creator == "Hugging Face (Free)":
            dialogue_text = self.hf_generate(base_prompt)

        else:
            raise ValueError(f"Unknown manuscript creator: {self.manuscript_creator}")

        dialogues = self.create_dialogue(dialogue_text)

        if not dialogues:
            raise RuntimeError(f"{self.manuscript_creator} returned no dialogues.")

        return dialogues

    def create_dialogue(self, dialogue_text):
        lines = dialogue_text.strip().split("\n")
        dialogues = []

        for line in lines:
            if ":" not in line:
                continue
            speaker, text = line.split(":", 1)
            speaker = speaker.strip().replace("*", "").replace("**", "").strip()
            text = text.strip()
            if not speaker or not text:
                continue
            if speaker not in self.voice_map:
                raise RuntimeError(f"Unknown speaker in dialogue: {speaker}")
            dialogues.append((speaker, text))

        if not dialogues:
            raise RuntimeError("Parsed dialogue is empty after processing.")
        return dialogues

    def cleanup_chunks(self):
        for f in glob.glob("podcast/chunks/*.mp3"):
            try:
                os.remove(f)
            except Exception as e:
                self.log(f"❌ Failed to delete {f}: {e}")

    def get_wikipedia_summary(self, url):
        page_title = unquote(url.split("/")[-1])
        wiki = wikipediaapi.Wikipedia(language="en", user_agent="AI-Podcast-Generator")
        page = wiki.page(page_title)
        if not page.exists():
            raise ValueError(f"Page '{page_title}' does not exist.")
        return page.summary

    def extract_text_from_pdf(self, path):
        return "".join(page.get_text() for page in fitz.open(path))

    def extract_text_from_txt(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def extract_youtube_transcript(self, url, save_path="podcast/youtube_transcript.txt"):
        match = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
        if not match:
            raise ValueError(f"Invalid YouTube URL: {url}")
        video_id = match.group(1)

        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        formatter = TextFormatter()
        transcript_text = formatter.format_transcript(transcript_list)

        with open(save_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)

        self.log(f"✅ YouTube transcript saved to {save_path}")
        return transcript_text

    def hf_generate(self, prompt):
        raise NotImplementedError("Hugging Face generation not implemented.")

    def text_to_speech(self, text, speaker_name, filename):
        if self.provider == "google":
            voice_id = self.voice_map[speaker_name]["google"]
            input_text = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(language_code="en-US", name=voice_id)
            config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
            response = self.gcp_client.synthesize_speech(input_text, voice, config)
            with open(filename, "wb") as f:
                f.write(response.audio_content)

        elif self.provider == "elevenlabs":
            voice_id = self.voice_map[speaker_name]["elevenlabs"]
            chunks = self.eleven_client.text_to_speech.convert(
                text=text, voice_id=voice_id, model_id="eleven_multilingual_v2"
            )
            with open(filename, "wb") as f:
                for chunk in chunks:
                    f.write(chunk)

        elif self.provider == "openai":
            voice_id = self.voice_map[speaker_name]["openai"]
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY not set.")
            response = requests.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini-tts", "input": text, "voice": voice_id, "response_format": "mp3"},
            )
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI TTS failed: {response.status_code} - {response.text}")
            with open(filename, "wb") as f:
                f.write(response.content)

        elif self.provider == "pyttsx3":
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            target = self.voice_map[speaker_name]["pyttsx3"].lower()
            voice = next((v for v in voices if target in v.name.lower()), None)
            if voice:
                engine.setProperty("voice", voice.id)
            temp_wav = filename.replace(".mp3", ".wav")
            engine.save_to_file(text, temp_wav)
            engine.runAndWait()
            AudioSegment.from_wav(temp_wav).export(filename, format="mp3")
            os.remove(temp_wav)

        else:
            raise ValueError(f"Unsupported TTS provider: {self.provider}")


def fetch_jamendo_track(tag="lofi"):
    try:
        base_url = "https://api.jamendo.com/v3.0/tracks/"
        params = {
            "client_id": os.getenv("JAMENDO_CLIENT_ID"),
            "format": "json",
            "limit": "1",
            "tags": tag,
            "audioformat": "mp3",
        }
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        if data["headers"]["results_count"] > 0:
            track = data["results"][0]
            return track["audio"], track["name"], track["artist_name"]
        else:
            print("⚠️ No tracks found for tag:", tag)
            return None, None, None
    except Exception as e:
        print("❌ Jamendo API error:", e)
        return None, None, None


def download_mp3(url, filename="background.mp3"):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return filename


def mix_background_music(podcast_path, output_path="podcast/final_with_bgmusic.mp3", volume_reduction_db=20):
    print("🎧 Adding Jamendo background music...")
    url, title, artist = fetch_jamendo_track("lofi")
    if not url:
        print("❌ Failed to fetch Jamendo track.")
        return
    bg_path = download_mp3(url, "podcast/bgmusic.mp3")
    podcast = AudioSegment.from_mp3(podcast_path)
    bg_music = AudioSegment.from_mp3(bg_path) - volume_reduction_db
    loops_needed = (len(podcast) // len(bg_music)) + 1
    bg_music_looped = bg_music * loops_needed
    bg_music_looped = bg_music_looped[: len(podcast)]
    mixed = podcast.overlay(bg_music_looped)
    mixed.export(output_path, format="mp3")
    os.remove(bg_path)
    print(f"✅ Background music added and saved to: {output_path}")
    print(f"🎵 Track used: {title} by {artist}")
