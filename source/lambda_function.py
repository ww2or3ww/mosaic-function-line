import os
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate,
    PostbackEvent,
    LocationMessage, LocationSendMessage, 
    MessageEvent, ImageMessage
)
import requests
from PIL import Image

LINE_CHANNEL_ACCESS_TOKEN   = os.environ['LINE_CHANNEL_ACCESS_TOKEN']
LINE_CHANNEL_SECRET         = os.environ['LINE_CHANNEL_SECRET']
LINE_BOT_API = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
LINE_HANDLER = WebhookHandler(LINE_CHANNEL_SECRET)

def lambda_handler(event, context):
    logger.info(event)
    signature = event["headers"]["X-Line-Signature"]
    body = event["body"]
    
    # テキストメッセージを受け取った時に呼ばれるイベント
    @LINE_HANDLER.add(MessageEvent, message=TextMessage)
    def on_message(line_event):
        # ユーザー情報を取得する
        profile = LINE_BOT_API.get_profile(line_event.source.user_id)
        logger.info(profile)

        message = line_event.message.text.lower()
        if message == '選択肢':
            LINE_BOT_API.reply_message(line_event.reply_token, make_select_message())
        elif message == '佐鳴湖':
            LINE_BOT_API.reply_message(line_event.reply_token, make_sanaruko_location_message())
        else:
            LINE_BOT_API.reply_message(line_event.reply_token, TextSendMessage("こんにちは！"))

    # 選択肢から選ばれた時(postback)に呼ばれるイベント    
    @LINE_HANDLER.add(PostbackEvent)
    def on_postback(line_event):
        data = line_event.postback.data
        LINE_BOT_API.reply_message(line_event.reply_token, TextSendMessage("{0}を選択しましたね！".format(data)))
        
    # 位置情報を受け取った時に呼ばれるイベント
    @LINE_HANDLER.add(MessageEvent, message=LocationMessage)
    def on_location(line_event):
        latlon = "({0}, {1})".format(line_event.message.latitude, line_event.message.longitude)
        LINE_BOT_API.reply_message(line_event.reply_token, TextSendMessage("その場所の緯度経度は {0} ですね！".format(latlon)))
        
    # 画像を受け取った時に呼ばれるイベント
    @LINE_HANDLER.add(MessageEvent, message=ImageMessage)
    def on_image(line_event):
        logger.info(line_event)
        image_path = get_image_from_line(line_event.message.id)
            
    
    LINE_HANDLER.handle(body, signature)
    return 0

def make_select_message():
    return TemplateSendMessage(
        alt_text="選択肢",
        template=ButtonsTemplate(
            title="選択肢のテスト",
            text="下から1つ選んでね！",
            actions=[
                {
                    "type": "postback",
                    "data": "morning",
                    "label": "朝"
                },
                {
                    "type": "postback",
                    "data": "noon",
                    "label": "昼"
                },
                {
                    "type": "postback",
                    "data": "night",
                    "label": "夜"
                }
            ]
        )
    )
    
def make_sanaruko_location_message():
    title = '佐鳴湖'
    address = '〒432-8002 静岡県浜松市中区富塚町５１９５'
    lat = 34.707433242045255
    lng = 137.68702025092614
    return LocationSendMessage(title=title, address=address, latitude=lat, longitude=lng)

def get_image_from_line(message_id):
    file_path = '/tmp/{0}.jpg'.format(message_id)
    url = 'https://api.line.me/v2/bot/message/{0}/content/'.format(message_id)
    header = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + LINE_CHANNEL_ACCESS_TOKEN
    }
    response = requests.get(url, headers=header)
    if response.status_code == 200:
        with open(file_path, 'wb') as file:
            file.write(response.content)
            
    return file_path