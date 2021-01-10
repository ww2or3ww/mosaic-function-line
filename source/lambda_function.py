import os
import datetime
from io import BytesIO

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
    ImageMessage, ImageSendMessage
)

LINE_CHANNEL_ACCESS_TOKEN   = os.environ['LINE_CHANNEL_ACCESS_TOKEN']
LINE_CHANNEL_SECRET         = os.environ['LINE_CHANNEL_SECRET']
LINE_BOT_API                = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
LINE_HANDLER                = WebhookHandler(LINE_CHANNEL_SECRET)

MSG_ANNOUNCE_WEB            = 'Web版は選んでモザイクをかけれるよ♪\nhttps://mosaic.w2or3w.com/'

import mosaic_function_line_proc as proc

def lambda_handler(event, context):
    logger.info(event)
    signature = event['headers']['X-Line-Signature']
    body = event['body']
    
    # テキストメッセージを受け取った時に呼ばれるイベント
    @LINE_HANDLER.add(MessageEvent, message=TextMessage)
    def on_message(line_event):
        user = get_profile_from_event(line_event)

        message = line_event.message.text.lower()
        LINE_BOT_API.reply_message(line_event.reply_token, make_select_message())

    # 選択肢から選ばれた時(postback)に呼ばれるイベント    
    @LINE_HANDLER.add(PostbackEvent)
    def on_postback(line_event):
        user = get_profile_from_event(line_event)
        selected_type = line_event.postback.data
        proc.update_user_selected_type(user['user_id'], selected_type)
        message = '{0}を選択しました。'.format(proc.get_type_label(selected_type))
        LINE_BOT_API.reply_message(line_event.reply_token, 
            TextSendMessage(message + '\nモザイクをかけたい画像を送ってね！'))
        
    # 画像を受け取った時に呼ばれるイベント
    @LINE_HANDLER.add(MessageEvent, message=ImageMessage)
    def on_image(line_event):
        user = get_profile_from_event(line_event)

        is_find_faces, address_work, address_preview = process_mosaic_to_image(user, line_event.message.id)
        
        if not is_find_faces:
            LINE_BOT_API.reply_message(line_event.reply_token, 
                TextSendMessage('顔が見つかりませんでした。\n' + MSG_ANNOUNCE_WEB))
        else:
            LINE_BOT_API.reply_message(
                line_event.reply_token, 
                    [
                        ImageSendMessage(
                            original_content_url = address_work, 
                            preview_image_url = address_preview
                            ), 
                        TextSendMessage(MSG_ANNOUNCE_WEB)
                    ]
                )
    
    LINE_HANDLER.handle(body, signature)
    return 0


def get_profile_from_event(line_event):
    profile = LINE_BOT_API.get_profile(line_event.source.user_id)
    logger.info(line_event)
    logger.info(profile)

    user = proc.select_user_info(profile.user_id)
    if not user:
        proc.put_user_info(profile.user_id, profile.display_name, profile.picture_url)
        user = proc.select_user_info(profile.user_id)
        
    return user


def make_select_message():
    return TemplateSendMessage(
        alt_text='モザイク',
        template=ButtonsTemplate(
            title='モザイク',
            text='モザイクパターンを選んでね！',
            actions= proc.get_actions()
        )
    )

def process_mosaic_to_image(user, message_id):
    message_content = LINE_BOT_API.get_message_content(message_id)

    image_stream = BytesIO(message_content.content)
    image_buffer = image_stream.getvalue()

    now = datetime.datetime.now().strftime('%y%m%d%H%M%S')
    filename_org = '{0}_org_{1}.jpg'.format(now, message_id)
    upload_key_org = 'line/{0}/{1}'.format(user['user_id'], filename_org)
    filename_work = '{0}_work_{1}.jpg'.format(now, message_id)
    upload_key_work = 'line/{0}/{1}'.format(user['user_id'], filename_work)
    selected_type = user['selected_type']
    
    return proc.mosaic_to_image(image_buffer, upload_key_org, upload_key_work, selected_type)

