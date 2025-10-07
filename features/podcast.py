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

class PodcastGenerator:
    def __init__(self, provider="pyttsx3", log_func=print):
        load_dotenv()
        self.provider = provider
        self.log = log_func
        self.stopped_early = False

        os.makedirs("podcast/chunks", exist_ok=True)
        os.makedirs("podcast", exist_ok=True)
        self.voice_map = {
            "Bonnie": {
                "google": "en-US-Wavenet-C",
                "elevenlabs": "lxYfHSkYm1EzQzGhdbfc",
                "pyttsx3": "Zira",
                "openai": "nova",
            },
            "Clyde": {
                "google": "en-US-Wavenet-D",
                "elevenlabs": "pVnrL6sighQX7hVz89cp",
                "pyttsx3": "David",
                "openai": "fable",
            },
            "Alice": {
                "google": "en-US-Wavenet-F",
                "elevenlabs": "aEO01A4wXwd1O8GPgGlF",
                "pyttsx3": "Hazel",
                "openai": "shimmer",
            },
            "Bob": {
                "google": "en-US-Wavenet-B",
                "elevenlabs": "UgBBYS2sOqTuMpoF3BR0",
                "pyttsx3": "David",
                "openai": "onyx",
            },
        }

        self.gcp_client = (
            texttospeech.TextToSpeechClient() if provider == "google" else None
        )
        self.eleven_client = (
            ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
            if provider == "elevenlabs"
            else None
        )
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

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
        import re
        from youtube_transcript_api.formatters import TextFormatter

        match = re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url)
        if not match:
            raise ValueError(f"Invalid YouTube URL: {url}")
        video_id = match.group(1)

        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
            formatter = TextFormatter()
            transcript_text = formatter.format_transcript(transcript_list)

            with open(save_path, "w", encoding="utf-8") as f:
                f.write(transcript_text)

            self.log(f"✅ YouTube transcript saved to {save_path}")
            return transcript_text

        except Exception as e:
            self.log(f"❌ Failed to fetch YouTube transcript: {e}")
            raise
      
        

    def summarize_and_format_dialogue(self, text, speakers, target_length):
        word_count_map = {
            "Short (5 min)": 700,
            "Medium (10 min)": 1500,
            "Long (20 min)": 3000,
        }
        target_words = word_count_map.get(target_length, 1000)
        speaker_list = ", ".join(speakers)

        base_prompt = f"""
        You are tasked with converting the following article into a detailed, engaging dialogue between {speaker_list}.

        Instructions:
        - Aim for approximately {target_words} words total.
        - Make the conversation natural and dynamic, with back-and-forth exchanges.
        - Include questions, clarifications, and detailed explanations.
        - They may disagree and debate the topic.
        - They can interrupt each other but without losing context.
        - Do NOT include any stage directions, sound effects, or descriptions such as (laughing), [coughs], *sighs*, or any text in brackets or parentheses.
        - Only output spoken dialogue in the format:
        SpeakerName: Their spoken line.

        Article content:
        {text}
    """
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(base_prompt)
        dialogue_text = response.text
        dialogues = self.create_dialogue(dialogue_text)

        # Fallback prompt if no usable dialogue was returned
        if not dialogues:
            self.log(
                "⚠️ Gemini didn't return usable dialogue. Retrying with fallback prompt..."
            )

            fallback_prompt = f"""
            Simulate a podcast-style **interview or conversation** between {speaker_list}
            based on the following text. The goal is to **explore ideas, ask questions, and reflect**
            on the topic in a way that's natural, thoughtful, and human.

            **Instructions:**
            - Do not summarize — instead, let the speakers discuss the concepts in depth.
            - Alternate turns. They may ask questions, challenge assumptions, or agree/disagree.
            - Format: SpeakerName: dialogue

            **Text to explore:**
            {text}
            """

            response = model.generate_content(fallback_prompt)
            dialogue_text = response.text
            dialogues = self.create_dialogue(dialogue_text)

            if not dialogues:
                raise RuntimeError(
                    "No dialogues detected. Gemini failed on both prompt attempts."
                )

        return dialogues

    def create_dialogue(self, dialogue_text):
        lines = dialogue_text.strip().split("\n")
        dialogues = []

        for line in lines:
            if ":" not in line:
                continue
            try:
                speaker, text = line.split(":", 1)
                speaker = speaker.strip().replace("*", "").replace("**", "").strip()
                text = text.strip()
                if not speaker or not text:
                    continue
                if speaker not in self.voice_map:
                    self.log(f"⚠️ Skipping unknown speaker: {speaker}")
                    continue
                dialogues.append((speaker, text))
            except Exception as e:
                self.log(f"⚠️ Skipping malformed line: {line.strip()} — {e}")

        return dialogues

    def text_to_speech(self, text, speaker_name, filename):
        if self.provider == "google":
            voice_id = self.voice_map[speaker_name]["google"]
            input_text = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                language_code="en-US", name=voice_id
            )
            config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )
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
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini-tts",
                    "input": text,
                    "voice": voice_id,
                    "response_format": "mp3",
                },
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"OpenAI TTS failed: {response.status_code} - {response.text}"
                )
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

    def generate_podcast(
        self,
        source,
        source_type,
        speakers,
        target_length,
        stop_callback=None,
        progress_callback=None,
        background_music=False,
        manual=False,
    ):
        self.stopped_early = False

        if source_type == "Wikipedia":
            self.log(f"Fetching Wikipedia summary for {source}...")
            content_text = self.get_wikipedia_summary(source)
        elif source_type == "PDF":
            self.log(f"Extracting text from PDF: {source}...")
            content_text = self.extract_text_from_pdf(source)
        elif source_type == "TXT":
            self.log(f"Extracting text from TXT file: {source}...")
            content_text = self.extract_text_from_txt(source)
        elif source_type == "YouTube":
            self.log(f"Fetching YouTube transcript for {source}...")
            content_text = self.extract_youtube_transcript(source)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")


        if manual:
            with open("podcast/manual_edit.txt", "r", encoding="utf-8") as f:
                dialogue_text = f.read()
            dialogues = self.create_dialogue(dialogue_text)
            self.log("📜 Using manually edited manuscript.")
        else:
            self.log("Summarizing and formatting as dialogue...")
            dialogues = self.summarize_and_format_dialogue(
                content_text, speakers, target_length
            )

        if not dialogues:
            raise RuntimeError("No dialogues detected. Check Gemini output formatting.")

        self.log(
            f"Generating {len(dialogues)} dialogue chunks with {self.provider.capitalize()} TTS..."
        )
        audio_segments = []

        for idx, (speaker, chunk) in enumerate(dialogues):
            if stop_callback and stop_callback():
                self.log(f"🛑 Stopped at chunk {idx+1}/{len(dialogues)}")
                self.stopped_early = True
                break
            if progress_callback:
                progress_callback(idx + 1, len(dialogues))
            self.log(f"  > {speaker}: Chunk {idx+1}/{len(dialogues)}")
            filename = f"podcast/chunks/chunk_{idx}.mp3"
            self.text_to_speech(chunk, speaker, filename)
            audio_segments.append(AudioSegment.from_mp3(filename))

        if self.stopped_early:
            self.log("🛑 Podcast generation stopped. No final file will be created.")
            self.cleanup_chunks()
            return

        self.log("Combining audio segments...")
        podcast = sum(audio_segments[1:], audio_segments[0])
        base_name = (
            source.split("/")[-1]
            if source_type == "Wikipedia"
            else os.path.splitext(os.path.basename(source))[0]
        )
        timestamp = datetime.now().strftime("%d-%m_%H-%M")
        temp_path = f"podcast/{base_name}_{len(speakers)}Speakers_{timestamp}_raw.mp3"
        podcast.export(temp_path, format="mp3")

        final_path = f"podcast/{base_name}_{len(speakers)}Speakers_{timestamp}.mp3"

        if background_music:
            self.log("🎧 Adding background music...")
            try:
                bg_final_path = final_path.replace(".mp3", "_bg.mp3")
                mix_background_music(temp_path, bg_final_path)
                os.remove(temp_path)
                final_path = bg_final_path
                self.log(f"✅ Final podcast with music saved: {final_path}")
            except Exception as e:
                self.log(f"⚠️ Failed to add background music: {e}")
                os.rename(temp_path, final_path)
                self.log(f"✅ Podcast saved without music: {final_path}")
        else:
            os.rename(temp_path, final_path)
            self.log(f"✅ Final podcast saved: {final_path}")

        self.cleanup_chunks()


JAMENDO_CLIENT_ID = os.getenv("JAMENDO_CLIENT_ID")


def fetch_jamendo_track(tag="lofi"):
    try:
        base_url = "https://api.jamendo.com/v3.0/tracks/"
        params = {
            "client_id": os.getenv("JAMENDO_CLIENT_ID"),
            "format": "json",
            "limit": "1",
            "tags": tag,
            "audioformat": "mp32",
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
        print(
            "🔍 Full response:",
            response.status_code,
            response.text if "response" in locals() else "no response",
        )
        return None, None, None


def download_mp3(url, filename="background.mp3"):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return filename


def mix_background_music(
    podcast_path, output_path="podcast/final_with_bgmusic.mp3", volume_reduction_db=20
):
    print("🎧 Adding Jamendo background music...")
    url, title, artist = fetch_jamendo_track("lofi")
    if not url:
        print("❌ Failed to fetch Jamendo track.")
        return

    bg_path = download_mp3(url, "bgmusic.mp3")

    podcast = AudioSegment.from_mp3(podcast_path)
    bg_music = AudioSegment.from_mp3(bg_path) - volume_reduction_db

    loops_needed = (len(podcast) // len(bg_music)) + 1
    bg_music_looped = bg_music * loops_needed
    bg_music_looped = bg_music_looped[: len(podcast)]

    mixed = podcast.overlay(bg_music_looped)
    mixed.export(output_path, format="mp3")

    print(f"✅ Background music added and saved to: {output_path}")
    print(f"🎵 Track used: {title} by {artist}")
