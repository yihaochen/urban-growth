
import json
import numpy as np
import matplotlib.pyplot as plt
import boto3
from datetime import datetime
from satsearch import Search
from tools import *

s3 = boto3.client('s3')

def get_scenes(event, context):
    '''
    '''
    args = parse_args(event)

    if 'bbox' in args.keys():
        bbox = args['bbox']
    else:
        geojson = event
        bbox = get_bbox_geojson(geojson)

    items = search_scenes(bbox)
    scene_list = [[item.datetime.ctime(), item.properties['landsat:product_id'], item.properties['eo:cloud_cover']] for item in items]

    response = prep_response(scene_list)

    return response


def calc_urban_score(event, context):
    '''
    '''
    args = parse_args(event)

    product_id = args['product_id']
    geojson = (args['geojson'])

    image_swir = get_image(product_id, 'B6', geojson)
    image_nir =  get_image(product_id, 'B5', geojson)

    ndbi = (image_swir-image_nir)/(image_swir+image_nir)

    urban_score = np.nan_to_num(ndbi).sum() + np.count_nonzero(image_swir)

    date = args['date']

    json_obj = {'urban_score': urban_score, 'date': date}

    response = prep_response(json_obj)

    fname = 'ndbi/%s_%s.png' % (date, datetime.now().strftime('%Y%m%d_%H%M%S'))
    plot_save_image_s3(ndbi, fname)

    return response


def plot_save_image_s3(image, fname, bucket_name='urban-growth'):

    # Plot figure
    fig = plt.figure(figsize=(10, 10))
    plt.imshow(image, vmin=-0.3, vmax=0.0, cmap='PiYG_r', interpolation='nearest')
    plt.axis('off')
    plt.savefig('/tmp/tmp.png')
    response = s3.upload_file('/tmp/tmp.png', bucket_name, fname)
    print(response)
