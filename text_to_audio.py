
import os
import json
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
from config import ELEVENLABS_API_KEY
from dotenv import load_dotenv
import subprocess
 

def ffmpeg_executable():
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def create_silent_audio(save_file_path: str, duration: float = 8.0) -> str:
    command = [
        ffmpeg_executable(),
        "-y",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", f"{duration:.2f}",
        "-q:a", "9",
        "-acodec", "libmp3lame",
        save_file_path
    ]

    subprocess.run(command, check=True)
    print("Fallback silent audio created:", save_file_path)
    return save_file_path


def write_voice_status(folder_path: str, provider: str, message: str = "") -> None:
    try:
        with open(os.path.join(folder_path, "voice_status.json"), "w", encoding="utf-8") as f:
            json.dump({"provider": provider, "message": message}, f)
    except OSError:
        pass


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def create_windows_voice_audio(text: str, save_file_path: str) -> str:
    folder_path = os.path.dirname(save_file_path)
    if not (text or "").strip():
        write_voice_status(folder_path, "Silent fallback", "No voiceover text was supplied.")
        return create_silent_audio(save_file_path, estimate_speech_duration(text))

    text_path = os.path.join(folder_path, "voice_text.txt")
    wav_path = os.path.splitext(save_file_path)[0] + ".wav"
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text[:4000])

    script = (
        "$text=Get-Content -LiteralPath " + ps_quote(text_path) + " -Raw;"
        "Add-Type -AssemblyName System.Speech;"
        "$speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$speaker.Rate=0;$speaker.Volume=100;"
        "$speaker.SetOutputToWaveFile(" + ps_quote(wav_path) + ");"
        "$speaker.Speak($text);"
        "$speaker.Dispose();"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
        subprocess.run(
            [ffmpeg_executable(), "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "4", save_file_path],
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
        if os.path.getsize(save_file_path) == 0:
            raise RuntimeError("Windows voice produced an empty MP3.")
        write_voice_status(folder_path, "Windows voice fallback", "ElevenLabs was unavailable, so Suhana generated spoken local voiceover.")
        return save_file_path
    except Exception as exc:
        write_voice_status(folder_path, "Silent fallback", f"Voice providers failed: {exc}")
        print("Windows voice fallback failed. Creating silent audio:", exc)
        return create_silent_audio(save_file_path, estimate_speech_duration(text))
    finally:
        try:
            if os.path.exists(wav_path):
                os.remove(wav_path)
        except OSError:
            pass


def estimate_speech_duration(text: str) -> float:
    words = len((text or "").split())
    return max(5.0, min(60.0, words * 0.42 + 2.0))


def text_to_speech_file(text: str, folder_path: str, api_key: str | None = None) -> str:
    save_file_path = os.path.join(folder_path, "audio.mp3")
    load_dotenv(override=True)
    active_api_key = api_key or os.getenv("ELEVENLABS_API_KEY") or ELEVENLABS_API_KEY

    if not active_api_key:
        print("No ElevenLabs key found. Using Windows voice fallback.")
        return create_windows_voice_audio(text, save_file_path)

    try:
        client = ElevenLabs(api_key=active_api_key)

        response = client.text_to_speech.convert(
            voice_id="pNInz6obpgDQGcFmaJgB",
            output_format="mp3_22050_32",
            text=text,
            model_id="eleven_turbo_v2_5",
            voice_settings=VoiceSettings(
                stability=0.0,
                similarity_boost=1.0,
                style=0.0,
                use_speaker_boost=True,
                speed=1.0,
            ),
        )

        with open(save_file_path, "wb") as f:
            for chunk in response:
                if chunk:
                    f.write(chunk)

        if os.path.getsize(save_file_path) == 0:
            raise RuntimeError("ElevenLabs returned an empty audio file.")

        write_voice_status(folder_path, "ElevenLabs", "Real ElevenLabs voiceover generated successfully.")
        print(f"{save_file_path}: A new audio file was saved successfully!")
        return save_file_path
    except Exception as exc:
        message = str(exc)[:500]
        print("ElevenLabs voiceover failed. Using Windows voice fallback:", message)
        return create_windows_voice_audio(text, save_file_path)
# text_to_speech_file("Hey I am a good boy and its the python course", "ac9a7034-2bf9-11f0-b9c0-ad551e1c593a")
