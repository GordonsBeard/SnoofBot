"""
SnoofBot - Handles uploading saved pictures to Telegram channel with sources

- Automatically scans folder and uploads image
- Uses e621 hash to source information and tag post
- Attempts to dowSnscale images to meet Telgram photo post requirements
- Converts all video files to a universally viewable format on Telegram within bot upload size limits
- Fixes odd-pixel scaling issues for a long unfixed iOS specific Telegram bug that squashes aspect ratios
- Moves files too large for upload somewhere else
"""

import os
import pathlib
import subprocess
import sys
import time

import requests
from PIL import Image, ImageOps

# Replace with your bot token
BOT_TOKEN = ""

# Replace with your E621 API Key (https://e621.net/api_keys)
E621_TOKEN = ""
E621_USERNAME = ""

# Replace with your group chat IDs (add more as needed ie, "-1234", "-5678")
CHAT_IDS = [""]

PICTURES_FOLDER = r""  # where the files are downloaded (usually Downloads/bs)
PROCESSED_FOLDER = r""  # where the files are moved after uploaded to Telegram


# Flags (optional)
DELETE_PICTURE = False  # keep the file after uploading? (defualt yes)
RENAME_PICTURE = True  # rename picture to (artist_name)-(e621_postID).ext
CUSTOM_MESSAGE = ""  # optional message appended to captions (leave empty to disable)

# Max file size (do not modify)
MAX_SIZE = 50 * 1024 * 1024
MAX_PHOTO_SIZE = 10485760

# Artist "names" to ignore (do not modify)
ignore_artist_names = [
    "avoid_posting",
    "conditional_dnp",
    "epilepsy_warning",
    "sound_warning",
    "jumpscare_warning",
    "unknown_artist_signature",
]


def send_file(file_path, e621_info):
    """Send a file to the Telegram group"""
    print(f"Sending: {file_path} to Telegram channel")
    post_extention = pathlib.Path(file_path).suffix

    if (
        file_extension in (".jpg", ".jpeg", ".png", ".webp")
        and os.path.getsize(file_path) < MAX_PHOTO_SIZE
    ):
        endpoint, field = "sendPhoto", "photo"
    elif post_extention in (".mp4", ".mov", ".avi"):
        endpoint, field = "sendVideo", "video"
    elif post_extention in (".gif"):
        endpoint, field = "sendAnimation", "animation"
    else:
        endpoint, field = "sendDocument", "document"

    caption = f"{e621_info['artists']}: <a href='https://e621.net/posts/{e621_info['post_id']}'>E621</a>"
    if CUSTOM_MESSAGE:
        caption += f"\n\n{CUSTOM_MESSAGE}"

    data = {"caption": caption, "parse_mode": "HTML"}

    if endpoint == "sendVideo":
        metadata = get_video_metadata(file_path)
        data.update(metadata)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{endpoint}"
    results = []
    for chat_id in CHAT_IDS:
        data["chat_id"] = chat_id
        with open(file_path, "rb") as file:
            response = requests.post(url, data=data, files={field: file}, timeout=300)
            results.append(response.json())
    return results


def fetch_e621_tags(file):
    """Gathers information about e621 downloaded image."""
    time.sleep(1)
    file_md5 = pathlib.Path(file).stem
    lookup_url = f"https://e621.net/posts.json?api_key={E621_TOKEN}&login={E621_USERNAME}&md5={file_md5}"
    response = requests.get(
        lookup_url,
        headers={"User-Agent": "SnoofBot/1.0 (ran by {E621_USERNAME} on e621)"},
        timeout=60,
    )

    if response.ok:
        info = response.json()
        artists = [
            artist_name
            for artist_name in info["post"]["tags"]["artist"]
            if artist_name not in ignore_artist_names
        ]
        post_id = info["post"]["id"]
        post_info = {"artists": "-".join(artists), "post_id": post_id}
    else:
        print("Couldn't get e621 info!")
        post_info = None
    return post_info


def get_video_metadata(file_path):
    """Extract video metadata using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        width, height = map(int, result.stdout.strip().split(","))

        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        duration = int(float(result.stdout.strip()))

        return {"width": width, "height": height, "duration": duration}
    except:
        return {}


def resize_image(file_path):
    """Resize image in-place until under MAX_PHOTO_SIZE."""
    file_ext = pathlib.Path(file_path).suffix.lower()
    original_size = os.path.getsize(file_path)
    print(f"Resizing {file_path} ({original_size / (1024*1024):.1f}MB)")

    with Image.open(file_path) as img:
        img = ImageOps.exif_transpose(img)
        img.load()
        width, height = img.size

    for i in range(20):
        width = int(width * 0.9)
        height = int(height * 0.9)
        resized = img.resize((width, height), Image.Resampling.LANCZOS)

        if file_ext in (".jpg", ".jpeg"):
            resized.save(file_path, format="JPEG", quality=85)
        elif file_ext == ".png":
            resized.save(file_path, format="PNG")
        elif file_ext == ".webp":
            resized.save(file_path, format="WEBP", quality=85)

        new_size = os.path.getsize(file_path)
        if new_size < MAX_PHOTO_SIZE and (width + height) <= 10000:
            print(f"Resized to {width}x{height} ({new_size / (1024*1024):.1f}MB)")
            return True

    print("Could not resize under 10MB after 20 iterations, this is a BIG boy.")
    return False


def convert_webm_to_mp4(file_path):
    """Convert webm to mp4 using ffmpeg."""
    print(f"Converting {file_path} to mp4")
    base_path = os.path.splitext(file_path)[0]
    new_path = f"{base_path}.mp4"

    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        # Probe to fix pixel dimensions to account for iOS specific telegram bug
        width, height = map(int, probe.stdout.strip().split(","))
        needs_fix = width % 2 != 0 or height % 2 != 0

        cmd = ["ffmpeg", "-i", file_path]
        if needs_fix:
            cmd.extend(["-vf", f"scale='trunc({width}/2)*2':'trunc({height}/2)*2'"])
            print(f"Fixing odd dimensions ({width}x{height})")

        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                "-y",
                new_path,
            ]
        )

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, check=False
        )

        if result.returncode == 0:
            os.remove(file_path)
            print(f"Converted to {new_path}")
            return new_path
        else:
            print(f"ffmpeg failed: {result.stderr}")
            return None
    except Exception as e:
        print(f"Conversion error: {e}")
        return None


def compress_video(file_path):
    """Compress video until under MAX_SIZE (50MB)."""
    original_size = os.path.getsize(file_path)
    print(f"Compressing {file_path} ({original_size / (1024*1024):.1f}MB)")

    # Phase 1: Reduce bitrate (8M → 6M → 4M)
    bitrates = ["8M", "6M", "4M"]
    for bitrate in bitrates:
        temp_path = f"{file_path}.temp.mp4"
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    file_path,
                    "-c:v",
                    "libx264",
                    "-b:v",
                    bitrate,
                    "-maxrate",
                    bitrate,
                    "-bufsize",
                    bitrate,
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    "-y",
                    temp_path,
                ],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )

            if result.returncode == 0 and os.path.exists(temp_path):
                os.replace(temp_path, file_path)
                new_size = os.path.getsize(file_path)
                if new_size < MAX_SIZE:
                    print(
                        f"Compressed with bitrate {bitrate} ({new_size / (1024*1024):.1f}MB)"
                    )
                    return True
        except Exception as e:
            print(f"Compression error: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # Phase 2: Scale down resolution
    for i in range(10):
        temp_path = f"{file_path}.temp.mp4"
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    file_path,
                    "-vf",
                    "scale='trunc(iw*0.9/2)*2':'trunc(ih*0.9/2)*2'",
                    "-c:v",
                    "libx264",
                    "-b:v",
                    "4M",
                    "-maxrate",
                    "4M",
                    "-bufsize",
                    "4M",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    "-y",
                    temp_path,
                ],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )

            if result.returncode == 0 and os.path.exists(temp_path):
                os.replace(temp_path, file_path)
                new_size = os.path.getsize(file_path)
                if new_size < MAX_SIZE:
                    print(f"Compressed with scaling ({new_size / (1024*1024):.1f}MB)")
                    return True
        except Exception as e:
            print(f"Compression error: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

    print("Could not compress under 50MB.")
    return False


def move_to_processed(starting_path, file_ext, tags):
    """Moves the file to its processed location"""
    new_filename = (
        f"{tags['artists']}_{tags['post_id']}.{file_ext}"
        if RENAME_PICTURE
        else file_name
    )

    destination_path = os.path.join(PROCESSED_FOLDER, new_filename)

    try:
        os.replace(starting_path, destination_path)
        print(f"Processed and moved {file_name} photo to {PROCESSED_FOLDER}")
        return True
    except OSError as err:
        print(f"Error moving file: {starting_path}. Error: {err}")
        return False


if __name__ == "__main__":
    if any(
        x == ""
        for x in [
            BOT_TOKEN,
            CHAT_IDS,
            E621_TOKEN,
            E621_USERNAME,
            PICTURES_FOLDER,
            PROCESSED_FOLDER,
        ]
    ):
        print("Make sure to fill out required variables at top of app.py")
        sys.exit()

    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    print(f"Program running: scanning {PICTURES_FOLDER} for pictures!")

    while True:
        for root, dirs, files in os.walk(PICTURES_FOLDER):
            for file_name in files:
                # If file contains .part/.crdownload exists, skip it
                if file_name.endswith(".part") or file_name.endswith(".crdownload"):
                    continue

                # If duplicated file found, delete it
                if "(1)" in file_name:
                    os.remove(os.path.join(root, file_name))
                    continue

                # Check if file 0 size or is still changing sizes
                full_path = os.path.join(root, file_name)
                initial_size = os.path.getsize(full_path)
                if os.path.getsize(full_path) == 0:
                    continue
                time.sleep(0.5)
                if os.path.getsize(full_path) != initial_size:
                    continue

                file_extension = pathlib.Path(full_path).suffix

                # Convert webm to mp4
                if file_extension == ".webm":
                    converted_path = convert_webm_to_mp4(full_path)
                    if converted_path:
                        full_path = converted_path
                        file_extension = ".mp4"
                    else:
                        continue

                # Compress video if > 50MB
                if (
                    file_extension in (".mp4", ".mov", ".avi")
                    and os.path.getsize(full_path) > MAX_SIZE
                ):
                    if not compress_video(full_path):
                        pass  # Continue to existing >50MB check which will move it

                if (
                    file_extension in (".jpg", ".jpeg", ".png", ".webp")
                    and os.path.getsize(full_path) > MAX_PHOTO_SIZE
                ):
                    if not resize_image(full_path):
                        continue

                # Grab the e621 metadata
                e621_tags = fetch_e621_tags(file_name)
                if e621_tags == {}:
                    print("Not an e621 image, not uploading.")
                    continue

                file_size = os.path.getsize(full_path)
                if file_size > MAX_SIZE:
                    print(f"Big Boy! ({file_size / (1024*1024):.1f}MB), moving")
                    if move_to_processed(full_path, file_extension, e621_tags):
                        continue
                    break

                # Sends the file to telegram
                send_results = send_file(full_path, e621_tags)

                all_succeeded = all(r.get("ok") for r in send_results)
                failed_results = [r for r in send_results if not r.get("ok")]

                if all_succeeded:
                    if DELETE_PICTURE:
                        print(f"Deleting {full_path}")
                        os.remove(full_path)
                    else:
                        move_to_processed(full_path, file_extension, e621_tags)
                else:
                    print(
                        f"Failed to send to some chats: {full_path}. Errors: {failed_results}"
                    )
        time.sleep(1)
