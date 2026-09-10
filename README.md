# SnoofBot
_Sniffing for smut, sources, and sharing._

##### What is this?
A bot that will handle uploading pictures (downloaded from e621) to a telegram channel of your choice. This will include the artist name as well as a link to the e621 post.

#### Setup

1. Download `app.py`
2. Edit `app.py` and fill out the following:
    * **BOT_TOKEN**: Create a Telegram bot, get the API key
    * **E621_TOKEN**: Get your e621 token from here: https://e621.net/api_keys
    * **E621_USERNAME**: e621 username
    * **CHAT_ID**: The Telegram chat ID (Use @username_to_id_bot if you don't know the chat ID)
    * **PICTURES_FOLDER**: Where are the pictures going to be uploaded from
    * **PROCESSED_FOLDER**: Where do you want the pictures to end up after being proccessed.
    * *(OPTIONAL)* **DELETE_PICTURE**: Do you want the picture to be deleted after being uploaded? (Default: False)
    * *(OPTIONAL)* **RENAME_PICTURE**: Do you want to rename the picture to {artist_name}-{e621_postID}.ext? (Default: True)
3. Run the script: `python ./app.py`
4. Download pictures from e621 into the **PICTURES_FOLDER**, the program should automatically scan and upload.


#### Limitations
* Photos larger than 10MB will be converted into a file attachment.
* Videos/files larger than 50MB will **not** be uploaded, but will be moved to the proccessed folder.
* Hasn't been thoroughly tested, do not try to upload your entire personal stash.