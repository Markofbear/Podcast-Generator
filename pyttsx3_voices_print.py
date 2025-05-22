import pyttsx3

engine = pyttsx3.init()
voices = engine.getProperty('voices')

print("🔊 Available pyttsx3 Voices:\n")
for i, voice in enumerate(voices):
    print(f"{i+1}. Name: {voice.name}")
    print(f"   ID:   {voice.id}")
    print(f"   Lang: {voice.languages}")
    print(f"   Gender: {getattr(voice, 'gender', 'Unknown')}")
    print(f"   Age:    {getattr(voice, 'age', 'Unknown')}")
    print("-" * 40)