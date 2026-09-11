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
import requests
import sys
import time
import subprocess
from PIL import Image, ImageOps

# Replace with your bot token
BOT_TOKEN = ""

# Replace with your E621 API Key (https://e621.net/api_keys)
E621_TOKEN = ""
E621_USERNAME = ""

# Replace with your group chat IDs (add more as needed ie, "-1234", "-5678")
CHAT_IDS = [""]

PICTURES_FOLDER = r"" # where the files are downloaded (usually Downloads/bs)
PROCESSED_FOLDER = r""           # where the files are moved after uploaded to Telegram

# Flags (optional)
DELETE_PICTURE = False                              # keep the file after uploading? (defualt yes)
RENAME_PICTURE = True                               # rename picture to (artist_name)-(e621_postID).ext
CUSTOM_MESSAGE = ""                                 # optional message appended to captions (leave empty to disable)

# Max file size (do not modify)
MAX_SIZE = 50 * 1024 * 1024
MAX_PHOTO_SIZE = 10485760

# Artist "names" to ignore (do not modify)
ignore_artist_names = ["avoid_posting", "conditional_dnp", "epilepsy_warning", "sound_warning", "jumpscare_warning", "unknown_artist_signature"]


def send_file(file_path, post_info):
    """Send a file to the Telegram group"""
    print(f"Sending: {file_path} to Telegram channel")
    ext = os.path.splitext(file_path)[1].lower()

    if ext in ('.jpg', '.jpeg', '.png', '.webp') and os.path.getsize(file_path) < MAX_PHOTO_SIZE:
        endpoint, field = 'sendPhoto', 'photo'
    elif ext in ('.mp4', '.mov', '.avi'):
        endpoint, field = 'sendVideo', 'video'
    elif ext in ('.gif'):
        endpoint, field = 'sendAnimation', 'animation'
    else:
        endpoint, field = 'sendDocument', 'document'

    caption = f"{post_info['artists']}: <a href='https://e621.net/posts/{post_info['post_id']}'>E621</a>"
    if CUSTOM_MESSAGE:
        caption += f"\n\n{CUSTOM_MESSAGE}"

    data = {
        "caption": caption,
        "parse_mode": "HTML"
    }

    if endpoint == 'sendVideo':
        metadata = get_video_metadata(file_path)
        data.update(metadata)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{endpoint}"
    results = []
    for chat_id in CHAT_IDS:
        data["chat_id"] = chat_id
        with open(file_path, "rb") as file:
            response = requests.post(url, data=data, files={field:file})
            results.append(response.json())
    return results

def e621_info(file):
    """Gathers information about e621 downloaded image."""
    time.sleep(1)
    md5 = file.split(".")[0]
    url = f"https://e621.net/posts.json?api_key={E621_TOKEN}&login={E621_USERNAME}&md5={md5}"
    response = requests.get(url, headers={"User-Agent": "SnoofBot/1.0 (by {E621_USERNAME} on e621)"})
    if response.ok:
        info = response.json()
        artists = [artist_name for artist_name in info["post"]["tags"]["artist"] if artist_name not in ignore_artist_names]
        post_id = info["post"]["id"]
        post_info = {"artists": "-".join(artists), "post_id": post_id}
    else:
        print(f"Couldn't get e621 info!")
        post_info = None
    return post_info

def get_video_metadata(file_path):
    """Extract video metadata using ffprobe."""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height', '-of', 'csv=p=0',
            file_path
        ], capture_output=True, text=True, timeout=10)
        width, height = map(int, result.stdout.strip().split(','))

        result = subprocess.run([
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'csv=p=0', file_path
        ], capture_output=True, text=True, timeout=10)
        duration = int(float(result.stdout.strip()))

        return {'width': width, 'height': height, 'duration': duration}
    except:
        return {}

def resize_image(file_path):
    """Resize image in-place until under MAX_PHOTO_SIZE."""
    ext = os.path.splitext(file_path)[1].lower()
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

        if ext in ('.jpg', '.jpeg'):
            resized.save(file_path, format='JPEG', quality=85)
        elif ext == '.png':
            resized.save(file_path, format='PNG')
        elif ext == '.webp':
            resized.save(file_path, format='WEBP', quality=85)

        new_size = os.path.getsize(file_path)
        if new_size < MAX_PHOTO_SIZE and (width + height) <= 10000:
            print(f"Resized to {width}x{height} ({new_size / (1024*1024):.1f}MB)")
            return True

    print(f"Could not resize under 10MB after 20 iterations, this is a BIG boy.")
    return False

def convert_webm_to_mp4(file_path):
    """Convert webm to mp4 using ffmpeg."""
    print(f"Converting {file_path} to mp4")
    base_path = os.path.splitext(file_path)[0]
    new_path = f"{base_path}.mp4"

    try:
        probe = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height', '-of', 'csv=p=0',
            file_path
        ], capture_output=True, text=True, timeout=30)
        # Probe to determine scaling and fixing pixel dimensions to account for iOS specific telegram bug
        width, height = map(int, probe.stdout.strip().split(','))
        needs_fix = width % 2 != 0 or height % 2 != 0

        cmd = ['ffmpeg', '-i', file_path]
        if needs_fix:
            cmd.extend(['-vf', f"scale='trunc({width}/2)*2':'trunc({height}/2)*2'"])
            print(f"Fixing odd dimensions ({width}x{height})")

        cmd.extend([
            '-c:v', 'libx264', '-c:a', 'aac',
            '-movflags', '+faststart', '-y',
            new_path
        ])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

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
    bitrates = ['8M', '6M', '4M']
    for bitrate in bitrates:
        temp_path = f"{file_path}.temp.mp4"
        try:
            result = subprocess.run([
                'ffmpeg', '-i', file_path,
                '-c:v', 'libx264', '-b:v', bitrate, '-maxrate', bitrate,
                '-bufsize', bitrate, '-c:a', 'aac',
                '-movflags', '+faststart', '-y',
                temp_path
            ], capture_output=True, text=True, timeout=300)

            if result.returncode == 0 and os.path.exists(temp_path):
                os.replace(temp_path, file_path)
                new_size = os.path.getsize(file_path)
                if new_size < MAX_SIZE:
                    print(f"Compressed with bitrate {bitrate} ({new_size / (1024*1024):.1f}MB)")
                    return True
        except Exception as e:
            print(f"Compression error: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # Phase 2: Scale down resolution
    for i in range(10):
        temp_path = f"{file_path}.temp.mp4"
        try:
            result = subprocess.run([
                'ffmpeg', '-i', file_path,
                '-vf', "scale='trunc(iw*0.9/2)*2':'trunc(ih*0.9/2)*2'",
                '-c:v', 'libx264', '-b:v', '4M', '-maxrate', '4M',
                '-bufsize', '4M', '-c:a', 'aac',
                '-movflags', '+faststart', '-y',
                temp_path
            ], capture_output=True, text=True, timeout=300)

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

    print(f"Could not compress under 50MB")
    return False

if __name__ == "__main__":
    if not BOT_TOKEN or not CHAT_IDS or not E621_TOKEN or not E621_USERNAME:
        print("Make sure to fill out BOT_TOKEN, CHAT_IDS, E621_TOKEN, E621_USERNAME, PICTURES_FOLDER, and PROCESSED_FOLDER!")
        sys.exit()

    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    print(f"Program running: scanning {PICTURES_FOLDER} for pictures!")
    while True:
        for root, dirs, files in os.walk(PICTURES_FOLDER):
            files = [x for x in files if x.endswith(".part") == False]
            for file in files:
                file_path = os.path.join(root, file)
                # Check if file is still downloading by comparing size
                initial_size = os.path.getsize(file_path)
                time.sleep(0.5)
                if os.path.getsize(file_path) != initial_size:
                    continue  # File still being written
                if "(1)" in file:
                    print("Duplicate file downloaded, deleting.")
                    os.remove(os.path.join(root, file))
                    continue
                elif os.path.getsize(file_path) == 0:
                    continue
                post_info = e621_info(file)
                if post_info == {}:
                    print("Not an e621 image, not uploading.")
                    continue

                ext = file_path.split(".")[-1]

                # Convert webm to mp4
                if ext == 'webm':
                    new_path = convert_webm_to_mp4(file_path)
                    if new_path:
                        file_path = new_path
                        ext = 'mp4'
                    else:
                        continue

                # Compress video if > 50MB
                if ext in ('mp4', 'mov', 'avi') and os.path.getsize(file_path) > MAX_SIZE:
                    if not compress_video(file_path):
                        pass  # Continue to existing >50MB check which will move it

                if ext in ('jpg', 'jpeg', 'png', 'webp') and os.path.getsize(file_path) > MAX_PHOTO_SIZE:
                    if not resize_image(file_path):
                        continue

                try:
                    file_size = os.path.getsize(file_path)
                    if file_size > MAX_SIZE:
                        new_filename = f"{post_info['artists']}_{post_info['post_id']}.{ext}" if RENAME_PICTURE else file # type: ignore
                        print(new_filename)
                        dest = os.path.join(PROCESSED_FOLDER, new_filename)
                        print(f"Big Boy! ({file_size / (1024*1024):.1f}MB), moving to: {dest}")
                        os.replace(file_path, dest)
                        continue
                except Exception as e:
                    print(f"Some kind of error moving the big file: {file_path} to {PROCESSED_FOLDER}")
                    break

                # Sends the file to telegram
                results = send_file(file_path, post_info)

                all_succeeded = all(r.get("ok") for r in results)
                failed_results = [r for r in results if not r.get("ok")]

                if all_succeeded:
                    if DELETE_PICTURE:
                        print(f"Deleting {file_path}")
                        os.remove(file_path)
                    else:
                        new_filename = f"{post_info['artists']}_{post_info['post_id']}.{ext}" if RENAME_PICTURE else file # type: ignore
                        dest = os.path.join(PROCESSED_FOLDER, new_filename)
                        print(f"Processed and moved {file} photo to {PROCESSED_FOLDER}")
                        os.replace(file_path, dest)
                else:
                    print(f"Failed to send to some chats: {file_path}. Errors: {failed_results}")
        time.sleep(1)

