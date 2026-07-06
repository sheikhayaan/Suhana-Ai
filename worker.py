import os
import subprocess

from text_to_audio import create_silent_audio, estimate_speech_duration, text_to_speech_file
from main import app, db, Reel, User, APIKey, decrypt_secret
from config import ELEVENLABS_API_KEY
from dotenv import load_dotenv

def ffmpeg_executable():
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def text_to_audio(folder_path, api_key=None):
    print("TTA - ", folder_path)

    with open(os.path.join(folder_path, "desc.txt"), encoding="utf-8") as f:
        text = f.read()

    text_to_speech_file(text, folder_path, api_key=api_key)


def estimate_audio_duration(folder_path):
    desc_path = os.path.join(folder_path, "desc.txt")
    try:
        with open(desc_path, encoding="utf-8") as f:
            words = len(f.read().split())
    except OSError:
        words = 12

    return max(5.0, min(60.0, words * 0.42 + 2.0))


def parse_input_files(folder_path):
    input_file = os.path.join(folder_path, "input.txt")
    files = []

    with open(input_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("file "):
                continue
            filename = line[5:].strip().strip("'").strip('"')
            if filename and filename not in files:
                files.append(filename)

    return files


def is_image_file(filename):
    return filename.rsplit(".", 1)[-1].lower() in {"png", "jpg", "jpeg", "webp"}


def reel_dimensions(folder_path=None):
    aspect_ratio = "9:16"
    if folder_path:
        try:
            with open(os.path.join(folder_path, "aspect_ratio.txt"), encoding="utf-8") as f:
                aspect_ratio = f.read().strip() or aspect_ratio
        except OSError:
            pass
    if aspect_ratio == "16:9":
        width = int(os.getenv("REEL_16_9_WIDTH", "640"))
        height = int(os.getenv("REEL_16_9_HEIGHT", "360"))
        return width, height
    width = int(os.getenv("REEL_WIDTH", "360"))
    height = int(os.getenv("REEL_HEIGHT", "640"))
    return width, height


def make_segment(source_path, output_path, duration, folder_path=None):
    width, height = reel_dimensions(folder_path)
    scale_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p"
    )

    if is_image_file(source_path):
        command = [
            ffmpeg_executable(),
            "-y",
            "-loop", "1",
            "-t", f"{duration:.2f}",
            "-i", source_path,
            "-vf", scale_filter,
            "-r", "30",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-threads", "1",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
    else:
        command = [
            ffmpeg_executable(),
            "-y",
            "-stream_loop", "-1",
            "-t", f"{duration:.2f}",
            "-i", source_path,
            "-an",
            "-vf", scale_filter,
            "-r", "30",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-threads", "1",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

    subprocess.run(command, check=True)


def create_reel(folder_path, output_path):
    audio_file = os.path.join(folder_path, "audio.mp3")
    input_files = parse_input_files(folder_path)

    if not input_files:
        raise ValueError("No visual files were found for reel generation.")

    estimated_duration = estimate_audio_duration(folder_path)
    if not os.path.exists(audio_file) or os.path.getsize(audio_file) == 0:
        try:
            with open(os.path.join(folder_path, "desc.txt"), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            text = ""
        create_silent_audio(audio_file, estimate_speech_duration(text))

    source_path = os.path.join(folder_path, input_files[0])
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Missing reel visual: {source_path}")

    width, height = reel_dimensions(folder_path)
    scale_filter = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p"
    )

    if is_image_file(source_path):
        command = [
            ffmpeg_executable(),
            "-y",
            "-loop", "1",
            "-t", f"{estimated_duration:.2f}",
            "-i", source_path,
            "-i", audio_file,
            "-vf", scale_filter,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-threads", "1",
            "-c:a", "aac",
            "-shortest",
            "-r", "24",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]
    else:
        command = [
            ffmpeg_executable(),
            "-y",
            "-stream_loop", "-1",
            "-t", f"{estimated_duration:.2f}",
            "-i", source_path,
            "-i", audio_file,
            "-vf", scale_filter,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-threads", "1",
            "-c:a", "aac",
            "-shortest",
            "-r", "24",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path,
        ]

    subprocess.run(command, check=True)

    print("CR - ", output_path)

def find_folder_for_reel(user_id, folder_id):
    user_folder = str(user_id)
    if user_id == 0:
        for candidate in os.listdir("user_uploads"):
            if candidate.startswith("guest_"):
                candidate_path = os.path.join("user_uploads", candidate, folder_id)
                if os.path.isdir(candidate_path):
                    return candidate, candidate_path

    folder_path = os.path.join("user_uploads", user_folder, folder_id)
    if os.path.isdir(folder_path):
        return user_folder, folder_path

    return None, None


def process_single_reel(folder_id):
    with app.app_context():
        reel = Reel.query.filter_by(folder_id=folder_id).first()
        if not reel or reel.status in ["completed", "failed"]:
            return

        user = User.query.get(reel.user_id) if reel.user_id else None
        owner_folder, folder_path = find_folder_for_reel(reel.user_id, folder_id)

        if not folder_path:
            reel.status = "failed"
            reel.error_message = "Upload folder was not found for this reel."
            db.session.commit()
            return

        user_api_key = None
        if user and user.generation_mode == "byok":
            saved_key = APIKey.query.filter_by(user_id=user.id, provider="elevenlabs").first()
            if saved_key:
                user_api_key = decrypt_secret(saved_key.key_value)
            else:
                load_dotenv(override=True)
                user_api_key = os.getenv("ELEVENLABS_API_KEY") or ELEVENLABS_API_KEY

        reel.status = "processing"
        reel.error_message = None
        db.session.commit()

    output_file = f"{owner_folder}_{folder_id}.mp4"
    output_path = os.path.join("static", "reels", output_file)

    try:
        text_to_audio(folder_path, api_key=user_api_key)
        create_reel(folder_path, output_path)

        with app.app_context():
            reel = Reel.query.filter_by(folder_id=folder_id).first()
            if reel:
                reel.status = "completed"
                reel.output_file = output_file
                reel.error_message = None
                db.session.commit()
                print("Database updated:", folder_id, output_file)
    except Exception as e:
        with app.app_context():
            reel = Reel.query.filter_by(folder_id=folder_id).first()
            if reel:
                reel.status = "failed"
                reel.error_message = str(e)[:1000]
                db.session.commit()
        print("Generation failed:", folder_id, e)


def process_queue_once():
    with app.app_context():
        reel = Reel.query.filter(Reel.status.in_(["pending", "processing"])).order_by(Reel.id.asc()).first()
        folder_id = reel.folder_id if reel else None

    if folder_id:
        process_single_reel(folder_id)
