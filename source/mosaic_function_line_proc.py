# --- coding: utf-8 ---
# mosaic-function-line > mosaic_function_line_proc
import os
from retry import retry
import urllib.parse
import cv2
import numpy as np

import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

import boto3
from boto3.dynamodb.conditions import Key
AWS_S3_BUCKET_NAME          = os.environ['AWS_S3_BUCKET_NAME']
AWS_S3_ADDRESS              = os.environ['AWS_S3_ADDRESS']
AWS_DYNAMODB_NAME           = os.environ['AWS_DYNAMODB_NAME']
S3 = boto3.client('s3')
REKOGNITION = boto3.client('rekognition')
DYNAMO_TABLE = boto3.resource('dynamodb').Table(AWS_DYNAMODB_NAME)

IMG_SIZE_PREV_MAX = 256

def get_actions():
    return [
        {
            'type': 'postback',
            'data': 'GaussianBlur_L',
            'label': 'ぼかし(大)'
        },
        {
            'type': 'postback',
            'data': 'GaussianBlur_S',
            'label': 'ぼかし(小)'
        },
        {
            'type': 'postback',
            'data': 'Tail_L',
            'label': 'タイル(大)'
        },
        {
            'type': 'postback',
            'data': 'Tail_S',
            'label': 'タイル(小)'
        }
    ]

def get_type_label(selected_type):
    actions = get_actions()
    actions = list(filter(lambda data: data['data'] == selected_type , actions))
    if len(actions) > 0:
        return actions[0]['label']
    

def mosaic_to_image(image_buffer, upload_key_org, upload_key_work, upload_key_prev, selected_type):
    file_bytes = np.asarray(bytearray(image_buffer), dtype=np.uint8)
    image_org = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    upload_image_to_s3(image_org, AWS_S3_BUCKET_NAME, upload_key_org)
    
    image_work = mosaic_faces(selected_type, AWS_S3_BUCKET_NAME, upload_key_org, image_org)
    if image_work is None:
        return False, None, None

    upload_image_to_s3(image_work, AWS_S3_BUCKET_NAME, upload_key_work)
    address_work = urllib.parse.urljoin(AWS_S3_ADDRESS, upload_key_work)
    address_preview = address_work

    height = image_work.shape[0]
    width = image_work.shape[1]
    if height > IMG_SIZE_PREV_MAX or width > IMG_SIZE_PREV_MAX:
        image_preview = resize_image(image_work, IMG_SIZE_PREV_MAX)
        upload_image_to_s3(image_preview, AWS_S3_BUCKET_NAME, upload_key_prev)
        address_preview = urllib.parse.urljoin(AWS_S3_ADDRESS, upload_key_prev)
    
    return True, address_work, address_preview

def mosaic_faces(selected_type, bucket, key, image_org):
    try:
        response = REKOGNITION.detect_faces(
            Image={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': key,
                }
            },
            Attributes=[
                'DEFAULT',
            ]
        )
        
        image_work = image_org.copy()
        image_mosaic = mosaic_image(image_org, selected_type)
        height = image_work.shape[0]
        width = image_work.shape[1]
        mask = np.tile(np.uint8(0), (height, width, 1))
        
        if len(response['FaceDetails']) == 0:
            return None
        
        for faceDetail in response['FaceDetails']:
            box = faceDetail['BoundingBox']
            x = max(int(width * box['Left']), 0)
            y = max(int(height * box['Top']), 0)
            w = int(width * box['Width'])
            h = int(height * box['Height'])
            contours = np.array(
                [
                    [x,     y],
                    [x + w, y],
                    [x + w, y + h],
                    [x,     y + h],
                ]
            )
            cv2.fillConvexPoly(mask, contours, color=(255, 255, 255))
        return np.where(mask != 0, image_mosaic, image_work)

    except Exception as e:
        logger.exception(e)
        raise e

def mosaic_image(image_org, selected_type):
    try:
        if selected_type.find('GaussianBlur') >= 0:
            prm = 51
            if selected_type.find('GaussianBlur_L') >= 0:
                prm = 101
            return cv2.GaussianBlur(image_org, (prm, prm), 0)
        elif selected_type.find('Tail') >= 0:
            prm = 0.1
            if selected_type.find('Tail_L') >= 0:
                prm = 0.05
            small = cv2.resize(image_org, None, fx=prm, fy=prm, interpolation=cv2.INTER_NEAREST)
            return cv2.resize(small, image_org.shape[:2][::-1], interpolation=cv2.INTER_NEAREST)
        else:
            logger.error(selected_type)
        
    except Exception as e:
        logger.exception(e)
        
def resize_image(image_work, target_size):
    height = image_work.shape[0]
    width = image_work.shape[1]
    size_max = max(height, width)
    mag = float(target_size) / float(size_max)
    return cv2.resize(image_work , (int(width * mag), int(height * mag)))

@retry(tries=3, delay=1)
def upload_image_to_s3(image, bucket, s3Key):
    localpath = os.path.join('/tmp/', os.path.basename(s3Key))
    try:
        cv2.imwrite(localpath, image)
        S3.upload_file(Filename=localpath, Bucket=bucket, Key=s3Key)
        
    except Exception as e:
        logger.exception(e)
        raise e
    finally:
        if os.path.exists(localpath):
            os.remove(localpath)

        
@retry(tries=3, delay=1)
def select_user_info(user_id):
    records = DYNAMO_TABLE.query(
        KeyConditionExpression=Key('user_id').eq(user_id)
    )
    if records is None or records['Count'] is 0:
        return None
        
    user = records['Items'][0]
    if 'selected_type' not in user:
        default_selected_type = 'GaussianBlur_L'
        user['selected_type'] = default_selected_type
        
    return user

@retry(tries=3, delay=1)
def put_user_info(user_id, display_name, picture_url):
    DYNAMO_TABLE.put_item(
      Item = {
        'user_id': user_id, 
        'display_name': display_name, 
        'picture_url': picture_url
      }
    )

@retry(tries=3, delay=1)
def update_user_selected_type(user_id, selected_type):
    DYNAMO_TABLE.update_item(
        Key={
            'user_id': user_id
        },
        UpdateExpression='set #selected_type = :selected_type',
        ExpressionAttributeNames={
            '#selected_type': 'selected_type'
        },
        ExpressionAttributeValues={
            ':selected_type': selected_type
        }
    )
