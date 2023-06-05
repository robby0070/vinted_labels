import base64
import logging
import os
import google.oauth2.credentials
from googleapiclient.discovery import build
from bs4 import BeautifulSoup
import html2text
import re
from wand.image import Image
from wand.color import Color

attachments = {}
credentials = google.oauth2.credentials.Credentials.from_authorized_user_file(
    'credentials.json', ['https://www.googleapis.com/auth/gmail.readonly'])
service = build('gmail', 'v1', credentials=credentials)


def htmlb64_to_plain(data):
    bytes = base64.urlsafe_b64decode(data)
    body_text = bytes.decode('utf-8')
    soup = BeautifulSoup(body_text, 'html.parser')
    return html2text.html2text(str(soup))


def download_attachments(part, msg_id):
    body = part['body']
    filename = os.path.join("attachments", part['filename'])
    attachment = service.users().messages().attachments().get(
        userId='me', messageId=msg_id, id=body['attachmentId']).execute()
    file_data = attachment['data']
    file_content = base64.urlsafe_b64decode(file_data)
    with open(filename, 'wb') as f:
        f.write(file_content)
        logging.info(
            f"successfully downloaded attachment with name: {filename}")
    return filename


def download_all_attachments():
    messages = service.users().messages().list(userId='me',
                                               labelIds=[
                                                   'Label_5694856354124115227'
                                               ],
                                               q="is:unread").execute()
    if 'messages' not in messages:
        logging.info("no messages found")
        return

    attachments = {}
    for message in messages['messages']:
        msg = service.users().messages().get(userId='me',
                                             id=message['id'],
                                             format='full').execute()
        logging.info(f"managing email with snippet:{msg['snippet']}")

        transaction_n = ""
        filename = ""
        msg_txt = ""
        for part in msg['payload']['parts']:
            data = part['body']
            if 'data' in data:
                msg_txt = htmlb64_to_plain(data['data'])
                match = re.search(
                    pattern=r"^\*\*N\. transazione:\*\* \| (\d*).*",
                    string=msg_txt,
                    flags=re.MULTILINE)
                if not match:
                    logging.critical(
                        "transaction number not found in email body, exiting")
                    exit(1)
                transaction_n = match.group(1)
            if 'filename' in part:
                body = part['body']
                if 'attachmentId' not in body:
                    continue
                filename = download_attachments(part=part, msg_id=msg["id"])
        attachments[transaction_n] = {
            "filename": filename,
            "body": msg_txt,
        }
        # TODO: risolvere errore sui permessi in modo da poter mettere come lette le email
        # service.users().messages().modify(
        #     userId = "me",
        #     id = msg["id"],
        #     body = { "removeLabelIds": ["UNREAD"] }
        # ).execute()

    return attachments


def main():
    attachments = download_all_attachments()
    for keys, values in attachments.items():
        # Save images
        with Image(filename=values["filename"], resolution=300) as img:
            img.format = 'jpeg'

            # Set background color to white
            img.background_color = Color("white")
            img.alpha_channel = 'remove'

            # Trim the image to remove surrounding whitespace
            img.trim()

            # Save the trimmed image
            img.save(filename='output.jpg')


if __name__ == "__main__":
    main()