import base64
import logging
import os
import google.oauth2.credentials
from googleapiclient.discovery import build


credentials = google.oauth2.credentials.Credentials.from_authorized_user_file('credentials.json', ['https://www.googleapis.com/auth/gmail.readonly'])
service = build('gmail', 'v1', credentials=credentials)
messages = service.users().messages().list(userId='me', labelIds = ['Label_5694856354124115227'], q="is:unread").execute()
if 'messages' not in messages:
    logging.info("no messages found")
    exit(0)
for message in messages['messages']:
    msg = service.users().messages().get(userId='me', id=message['id']).execute()
    for part in msg['payload']['parts']:
        if 'filename' in part:
            body = part['body']
            if 'attachmentId' not in body:
                continue
            filename = part['filename']
            attachment = service.users().messages().attachments().get(
                userId='me', messageId=msg['id'], id=body['attachmentId']
            ).execute()
            file_data = attachment['data']
            file_content = base64.urlsafe_b64decode(file_data)
            # Save the attachment to disk
            with open(filename, 'wb') as f:
                f.write(file_content)
                print(f"Attachment '{filename}' downloaded successfully.")

    print(msg['snippet'])
