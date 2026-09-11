"""
SnoofBot - Handles uploading saved pictures to Telegram channel with sources

- Automatically scans folder and uploads image
- Uses e621 hash to source information and tag post
- Moves files too large for upload somewhere else
"""

import os
import sys
import time

import requests

# Replace with your bot token
BOT_TOKEN = ""

# Replace with your E621 API Key (https://e621.net/api_keys)
E621_TOKEN = ""
E621_USERNAME = ""

# Replace with your group chat ID
CHAT_ID = ""

PICTURES_FOLDER = r""  # where the files are downloaded (usually Downloads/bs)
PROCESSED_FOLDER = r""  # where the files are moved after uploaded to Telegram

# Flags (optional)
DELETE_PICTURE = False  # keep the file after uploading? (defualt yes)
RENAME_PICTURE = True  # rename picture to (artist_name)-(e621_postID).ext

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


def send_file(file_path, post_info):
    """Send a file to the Telegram group"""
    print(f"Sending: {file_path} to Telegram channel")
    ext = os.path.splitext(file_path)[1].lower()

    if ext in (".jpg", ".jpeg", ".png", ".webp"):
        if os.path.getsize(file_path) < MAX_PHOTO_SIZE:
            endpoint, field = "sendPhoto", "photo"
        else:
            endpoint, field = "sendDocument", "document"
    elif ext in (".mp4", ".mov", ".avi", ".webm"):
        endpoint, field = "sendVideo", "video"
    elif ext in (".gif"):
        endpoint, field = "sendAnimation", "animation"
    else:
        return -1

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{endpoint}"
    with open(file_path, "rb") as file:
        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "caption": f"{post_info["artists"]}: <a href='https://e621.net/posts/{post_info["post_id"]}'>E621</a>",
                "parse_mode": "HTML",
            },
            files={field: file},
            timeout=10,
        )
        return response.json()


def e621_info(file):
    """Gathers information about e621 downloaded image."""
    time.sleep(1)
    md5 = file.split(".")[0]
    url = f"https://e621.net/posts.json?api_key={E621_TOKEN}&login={E621_USERNAME}&md5={md5}"
    response = requests.get(
        url,
        headers={"User-Agent": f"SnoofBot/1.0 (by {E621_USERNAME} on e621)"},
        timeout=10,
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
        print(f"Couldn't get e621 info! Response:({response})")
        post_info = -1
    return post_info


if __name__ == "__main__":
    if (
        not BOT_TOKEN
        or not CHAT_ID
        or not E621_TOKEN
        or not E621_USERNAME
        or not PICTURES_FOLDER
        or not PROCESSED_FOLDER
    ):
        print(
            "Make sure to fill out BOT_TOKEN, CHAT_ID, E621_TOKEN, E621_USERNAME, PICTURES_FOLDER, and PROCESSED_FOLDER!"
        )
        sys.exit()

    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    print(f"Program running: scanning {PICTURES_FOLDER} for pictures!")
    while True:
        for root, dirs, files in os.walk(PICTURES_FOLDER):
            files = [x for x in files if x.endswith(".part") is False]
            for file in files:
                file_path = os.path.join(root, file)
                if "(1)" in file:
                    print("Duplicate file downloaded, deleting.")
                    os.remove(os.path.join(root, file))
                    continue
                if os.path.getsize(file_path) == 0:
                    continue
                post_info = e621_info(file)
                if post_info == -1:
                    print("Not an e621 image, not uploading.")
                    os.replace(file_path, os.path.join(PROCESSED_FOLDER, file))
                    continue

                try:
                    ext = file_path.split(".")[-1]
                    file_size = os.path.getsize(file_path)
                    if file_size > MAX_SIZE:
                        new_filename = (
                            f"{post_info['artists']}_{post_info['post_id']}.{ext}"
                            if RENAME_PICTURE
                            else file
                        )
                        print(new_filename)
                        dest = os.path.join(PROCESSED_FOLDER, new_filename)
                        print(
                            f"Big Boy! ({file_size / (1024*1024):.1f}MB), moving to: {dest}"
                        )
                        os.replace(file_path, dest)
                        continue
                except Exception as e:
                    print(
                        f"Some kind of error moving the big file: {file_path} to {PROCESSED_FOLDER}"
                    )
                    break

                # Sends the file to telegram
                result = send_file(file_path, post_info)
                if result == -1:
                    os.replace(file_path, os.path.join(PROCESSED_FOLDER, file))
                elif result.get("ok"):
                    if DELETE_PICTURE:
                        print("Deleting after upload.")
                        os.remove(file_path)
                    else:
                        new_filename = (
                            f"{post_info['artists']}_{post_info['post_id']}.{ext}"
                            if RENAME_PICTURE
                            else file
                        )
                        dest = os.path.join(PROCESSED_FOLDER, new_filename)
                        print(f"Processed and moved {file} photo to {PROCESSED_FOLDER}")
                        os.replace(file_path, dest)
                else:
                    print(f"Failed to send?: {file_path}. Error: {result}")
        time.sleep(1)
