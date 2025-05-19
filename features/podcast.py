import os
import wikipediaapi
import fitz
import glob
import pyttsx3
from pydub import AudioSegment
from datetime import datetime
from urllib.parse import unquote


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
                "elevenlabs": "EXAVITQu4vr4xnSDxMaL",
                "pyttsx3": "Zira",
                "openai": "alloy",
            },
            "Clyde": {
                "google": "en-US-Wavenet-D",
                "elevenlabs": "TxGEqnHWrfWFTfGW9XjX",
                "pyttsx3": "David",
                "openai": "echo",
            },
            "Alice": {
                "google": "en-US-Wavenet-F",
                "elevenlabs": "EXAVITQu4vr4xnSDxMaL",
                "pyttsx3": "Zira",
                "openai": "nova",
            },
            "Bob": {
                "google": "en-US-Wavenet-B",
                "elevenlabs": "TxGEqnHWrfWFTfGW9XjX",
                "pyttsx3": "Mark",
                "openai": "shimmer",
            },
        }

        self.gcp_client = texttospeech.TextToSpeechClient() if provider == "google" else None
        self.eleven_client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY")) if provider == "elevenlabs" else None
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

    def summarize_and_format_dialogue(self, text, speakers, target_length):
        word_count_map = {
            "Short (5 min)": 700,
            "Medium (10 min)": 1500,
            "Long (20 min)": 3000,
        }
        target_words = word_count_map.get(target_length, 1000)
        speaker_list = ", ".join(speakers)

        prompt = f"""
        You are tasked with converting the following article into a **detailed, engaging dialogue** between {speaker_list}.

        **Instructions:**
        - Aim for a total length of **approximately {target_words} words**.
        - Make the conversation **natural and dynamic**, with **back-and-forth exchanges**.
        - Include **questions, clarifications, and detailed explanations**.
        - Use this speaker format:  
        SpeakerName: Their line of dialogue.

        **Article content:**
        {text}
        """

        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        return response.text

    def create_dialogue(self, dialogue_text):
        lines = dialogue_text.strip().split("\n")
        return [
            (speaker.strip().strip("*"), text.strip())
            for line in lines if ":" in line
            for speaker, text in [line.split(":", 1)]
        ]

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
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini-tts",
                    "input": text,
                    "voice": voice_id,
                    "response_format": "mp3"
                }
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

    def generate_podcast(self, source, source_type, speakers, target_length, stop_callback=None, progress_callback=None):
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
        else:
            raise ValueError(f"Unsupported source type: {source_type}")

        self.log("Summarizing and formatting as dialogue...")
        dialogue_text = self.summarize_and_format_dialogue(content_text, speakers, target_length)
        dialogues = self.create_dialogue(dialogue_text)
        if not dialogues:
            raise RuntimeError("No dialogues detected. Check Gemini output formatting.")

        self.log(f"Generating {len(dialogues)} dialogue chunks with {self.provider.capitalize()} TTS...")
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
        base_name = source.split("/")[-1] if source_type == "Wikipedia" else os.path.splitext(os.path.basename(source))[0]
        timestamp = datetime.now().strftime("%d-%m_%H-%M")
        output_path = f"podcast/{base_name}_{len(speakers)}Speakers_{timestamp}.mp3"
        podcast.export(output_path, format="mp3")
        self.log(f"✅ Podcast created: {output_path}")
        self.cleanup_chunks()
