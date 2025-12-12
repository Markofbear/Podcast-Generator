import os
import glob
import fitz
import pyttsx3
import requests
import wikipediaapi
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
import pathlib

load_dotenv()

class PodcastGenerator:
    def __init__(self, provider="pyttsx3", log_func=print, manuscript_creator="OpenAI GPT-4"):
        self.provider = provider
        self.log = log_func
        self.manuscript_creator = manuscript_creator
        os.makedirs("podcast/chunks", exist_ok=True)
        os.makedirs("podcast", exist_ok=True)

        self.voice_map = {
            "Bonnie": {
                "pyttsx3": "Zira",
                "google": "en-US-Wavenet-F",
                "elevenlabs": "Bella",
                "openai": "alloy",
            },
            "Clyde": {
                "pyttsx3": "David",
                "google": "en-US-Wavenet-D",
                "elevenlabs": "Elliot",
                "openai": "verse",
            },
            "Alice": {
                "pyttsx3": "Microsoft Hazel Desktop",
                "google": "en-US-Wavenet-C",
                "elevenlabs": "Clara",
                "openai": "echo",
            },
            "Bob": {
                "pyttsx3": "Microsoft Guy Desktop",
                "google": "en-US-Wavenet-B",
                "elevenlabs": "Leo",
                "openai": "shimmer",
            },
        }

    def summarize_and_format_dialogue(self, text, speakers, target_words):
        if not text.strip():
            raise RuntimeError("Empty text")

        speaker_list = ", ".join(speakers)

        base_prompt = f"""
You are tasked with creating an engaging, informative dialogue script for a podcast. 
The dialogue is strictly between {speaker_list}, which are: Bonnie, Clyde, Alice, and Bob.
Do NOT introduce any other speakers, section headers, titles, or extra text.

Your goal is to clearly and fully convey all relevant information from the source document {text}, 
ensuring that someone reading or listening can learn everything important for onboarding or understanding the topic.

Requirements:
- Each line must start with a valid speaker: "SpeakerName: dialogue line"
- Target AT LEAST {target_words} words. If necessary, expand explanations, examples, and dialogue naturally to reach this word count.
- Include ALL relevant points from the source document; do not omit any critical information.
- Keep the dialogue natural and conversational, like a discussion between colleagues.
- Avoid fluff, repetition, or unrelated content.
- Ensure the dialogue flows logically from introduction to conclusion, covering all topics in the source.

Output example:
Bonnie: Starts the discussion naturally.
Clyde: Adds context or elaborates.
Alice: Explains or clarifies details.
Bob: Summarizes or provides examples.

Use this structure for the entire dialogue. Every important detail from the source must be included, and the output must be at least {target_words} words long.


Source Document:
{text}
"""

        if self.manuscript_creator.startswith("OpenAI"):
            resp = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": base_prompt}],
                temperature=0.7,
            )
            dialogue_text = resp.choices[0].message.content
        elif self.manuscript_creator == "Gemini 2.0":
            model = genai.GenerativeModel("gemini-2.0-flash")
            dialogue_text = model.generate_content(base_prompt).text
        elif self.manuscript_creator.startswith("Hugging Face"):
            dialogue_text = self.hf_generate(base_prompt)
        else:
            raise RuntimeError("Invalid manuscript creator")

        return self.create_dialogue(dialogue_text)


    def create_dialogue(self, dialogue_text):
        lines = dialogue_text.strip().split("\n")
        dialogues = []
        for line in lines:
            if ":" not in line:
                continue
            speaker, text = line.split(":", 1)
            speaker = speaker.strip().replace("*", "").replace("**", "").strip()
            text = text.strip()
            if not text:
                continue
            if speaker not in self.voice_map:
                self.log(f"⚠ Unknown speaker '{speaker}', using default voice 'Bonnie'")
                speaker = "Bonnie"
            dialogues.append((speaker, text))
        if not dialogues:
            raise RuntimeError("Empty parsed dialogue")
        return dialogues




    def cleanup_chunks(self):
        for f in glob.glob("podcast/chunks/*.mp3"):
            try:
                os.remove(f)
            except:
                pass

    def get_wikipedia_summary(self, url):
        title = unquote(url.split("/")[-1])
        wiki = wikipediaapi.Wikipedia(language="en", user_agent="AI-Podcast")
        page = wiki.page(title)
        if not page.exists():
            raise RuntimeError("Wikipedia page missing")
        return page.summary

    def extract_text_from_pdf(self, path):
        return "".join(page.get_text() for page in fitz.open(path))

    def extract_text_from_txt(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def extract_youtube_transcript(self, url):
        m = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
        if not m:
            raise ValueError("Invalid YouTube URL")
        video_id = m.group(1)
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        formatter = TextFormatter()
        return formatter.format_transcript(transcript)

    def hf_generate(self, prompt):
        raise NotImplementedError()

    def text_to_speech(self, text, speaker_name, filename):
        if self.provider == "google":
            voice_id = self.voice_map[speaker_name]["google"]
            inp = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(language_code="en-US", name=voice_id)
            config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
            audio = self.gcp_client.synthesize_speech(inp, voice, config)
            with open(filename, "wb") as f:
                f.write(audio.audio_content)
        elif self.provider == "elevenlabs":
            voice_id = self.voice_map[speaker_name]["elevenlabs"]
            stream = self.eleven_client.text_to_speech.convert(text=text, voice_id=voice_id, model_id="eleven_multilingual_v2")
            with open(filename, "wb") as f:
                for chunk in stream:
                    f.write(chunk)
        elif self.provider == "openai":
            voice_id = self.voice_map[speaker_name]["openai"]
            r = requests.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {openai.api_key}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini-tts", "input": text, "voice": voice_id, "response_format": "mp3"},
            )
            if r.status_code != 200:
                raise RuntimeError("OpenAI TTS error")
            with open(filename, "wb") as f:
                f.write(r.content)
        elif self.provider == "pyttsx3":
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            target = self.voice_map[speaker_name]["pyttsx3"].lower()
            v = next((x for x in voices if target in x.name.lower()), None)
            if v:
                engine.setProperty("voice", v.id)
            wav = filename.replace(".mp3", ".wav")
            engine.save_to_file(text, wav)
            engine.runAndWait()
            AudioSegment.from_wav(wav).export(filename, format="mp3")
            os.remove(wav)
        else:
            raise RuntimeError("Invalid provider")

    def download_mp3(self, url, filename):
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(filename, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
        return filename

    def fetch_jamendo_track(self, tag):
        try:
            base = "https://api.jamendo.com/v3.0/tracks/"
            params = {
                "client_id": os.getenv("JAMENDO_CLIENT_ID"),
                "format": "json",
                "limit": "1",
                "tags": tag,
                "audioformat": "mp32",
            }
            r = requests.get(base, params=params)
            r.raise_for_status()
            data = r.json()
            if data["headers"]["results_count"] > 0:
                t = data["results"][0]
                return t.get("audio")
            return None
        except:
            return None

    def mix_background_music(self, podcast_path, background_music=True, volume_reduction_db=20):
        if not background_music:
            return

        url = None
        for tag in ["lofi", "chill", "instrumental"]:
            url = self.fetch_jamendo_track(tag)
            if url:
                break
        if not url:
            return

        bg = self.download_mp3(url, "podcast/bgmusic.mp3")
        podcast = AudioSegment.from_mp3(podcast_path)
        music = AudioSegment.from_mp3(bg) - volume_reduction_db

        loops = (len(podcast) // len(music)) + 1
        looped = (music * loops)[:len(podcast)]

        mixed = podcast.overlay(looped)
        mixed.export(podcast_path, format="mp3")
        os.remove(bg)

    def generate_podcast(
        self,
        source,
        source_type,
        speakers,
        target_length,
        stop_callback=None,
        progress_callback=None,
        background_music=True,
        manual=False,
    ):
        os.makedirs("podcast/chunks", exist_ok=True)
        os.makedirs("podcast", exist_ok=True)

        if source_type == "PDF":
            text = self.extract_text_from_pdf(source)
        elif source_type == "TXT":
            text = self.extract_text_from_txt(source)
        elif source_type == "Wikipedia":
            text = self.get_wikipedia_summary(source)
        elif source_type == "YouTube":
            text = self.extract_youtube_transcript(source)
        else:
            raise RuntimeError("Invalid source type")

        dialogues = self.summarize_and_format_dialogue(text, speakers, target_length)
        self.cleanup_chunks()

        chunk_files = []
        total = len(dialogues)

        for i, (speaker, line) in enumerate(dialogues):
            if stop_callback and stop_callback():
                self.stopped_early = True
                return
            filename = f"podcast/chunks/{i}.mp3"
            self.text_to_speech(line, speaker, filename)
            chunk_files.append(filename)
            if progress_callback:
                progress_callback(i + 1, total)

        combined = AudioSegment.empty()
        for c in chunk_files:
            combined += AudioSegment.from_mp3(c)

        base = pathlib.Path(source).stem if source_type != "Wikipedia" else "wikipedia_podcast"
        output_path = f"podcast/{base}.mp3"
        counter = 1
        while os.path.exists(output_path):
            output_path = f"podcast/{base}({counter}).mp3"
            counter += 1

        combined.export(output_path, format="mp3")

        if background_music:
            self.mix_background_music(output_path, background_music=True)

        self.log(f"✅ Podcast ready: {output_path}")
