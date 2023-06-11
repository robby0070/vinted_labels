# general utility libraries
import base64
import logging
import os
import re
from datetime import datetime
import io

# libraries for google credentials management
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# libraries to deal with emails
from googleapiclient.discovery import build
from bs4 import BeautifulSoup
import html2text

# libraries to deal with images
from wand.image import Image
from wand.color import Color
from wand.drawing import Drawing

import PIL.Image

# librearies to make the telegram bot
from telegram import ForceReply, Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]
service = None
attachments = {}


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
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.

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
        subject = ""
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
        for header in msg["payload"]["headers"]:
            if header['name'].lower() == 'subject':
                subject = header['value']
                break
        attachments[transaction_n] = {
            "filename": filename,
            "body": msg_txt,
            "snippet": msg["snippet"],
            "subject": subject,
        }
        service.users().messages().modify(userId="me",
                                          id=msg["id"],
                                          body={
                                              "removeLabelIds": ["UNREAD"]
                                          }).execute()

    return attachments


def pdf_to_img_with_title(path, title, max_width: int, max_height: int):
    space_for_title = 50
    with Image(
            filename=path,
            resolution=300,
            colorspace='rgb',
    ) as img:
        img.format = 'jpeg'
        img.trim()
        if img.height > img.width:
            img.rotate(degree=90)
        perc_to_resize = min(
            max_width / img.width,
            (max_height - space_for_title) / img.height,
        )
        img.resize(width=int(img.width * perc_to_resize),
                   height=int(img.height * perc_to_resize))
        top_border_img = Image(width=max_width,
                               height=max_height + space_for_title,
                               background=Color("white"))
        top_border_img.composite(
            img,
            left=0,
            top=50,
        )

        with Drawing() as draw:
            # Set the text properties
            draw.font = 'Arial-bold'
            draw.font_size = 40
            draw.text_antialias = True
            draw.fill_color = Color('black')
            draw.stroke_color = Color('white')

            # Write the text on the image
            draw.text_interline_spaceing = 30
            draw.text(body=title, x=20, y=40)

            # Draw the text on the image
            draw(top_border_img)

        return top_border_img


allowed_users = [638353353]


def create_pdf():
    page_width = 2480
    page_height = 3508
    margin_top = 250
    margin_side = 250
    attachments = download_all_attachments()

    pdf_pages = []

    def create_pdf_page(img1, img2=None):
        with Image(
                width=page_width,
                height=page_height,
                background=Color("white"),
        ) as pdf_page:
            pdf_page.composite(
                img1,
                top=margin_top // 2,
                left=margin_side // 2,
            )
            img1.close()
            if img2:
                pdf_page.composite(
                    img2,
                    top=page_height // 2 + margin_top // 2,
                    left=margin_side // 2,
                )
                img2.close()
            pdf_pages.append(
                PIL.Image.open(io.BytesIO(pdf_page.make_blob("png"))))

    prev = None
    for _, a in attachments.items():
        img = pdf_to_img_with_title(
            path=a["filename"],
            title=a["subject"],
            max_height=page_height // 2 - margin_top,
            max_width=page_width - margin_side,
        )
        if not prev:
            prev = img
            continue
        create_pdf_page(img1=prev, img2=img)
        prev = None
    if prev:
        create_pdf_page(img1=prev)
    buffer = io.BytesIO()
    pdf_pages[0].save(
        buffer,
        save_all=True,
        append_images=pdf_pages[1:],
        format="PDF",
    )
    buffer.seek(0)
    return buffer


async def prepare_pdf(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id not in allowed_users:
        await update.message.reply_html(f"private bot, go away: {user.id}")

    # await update.message.reply_html(f"preparing pdf for: {user.id}")
    pdf_blob = create_pdf()
    # await update.message.reply_html(f"pdf completed, sending...")
    filename = f"vinted_{datetime.now().strftime(r'%Y-%m-%d_%H-%M-%S')}.pdf"
    print(filename)
    await update.message.reply_document(document=InputFile(
        pdf_blob,
        filename,
    ), )


async def help_command(update: Update,
                       context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Help!")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )


def main() -> None:
    global service
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)
    with open("token.txt", "r") as token_file:
        application = Application.builder().token(token_file.read()).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("pdf", prepare_pdf))

    # application.add_handler(
    #     MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    application.run_polling()

    # Save images


if __name__ == "__main__":
    main()