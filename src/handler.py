
import json
import numpy as np
from datetime import datetime
from tools import *


def get_scenes(event, context):
    '''
    An AWS Lambda function that takes a bbox and returns a list scenes covering
    the bbox.
    '''
    args = parse_args(event)

    if 'bbox' in args.keys():
        bbox = args['bbox']
    else:
        geojson = event
        bbox = get_bbox_geojson(geojson)

    items = search_scenes(bbox)
    scene_list = [[item.datetime.ctime(),\
                   item.properties['landsat:product_id'],\
                   item.properties['eo:cloud_cover']]\
                  for item in items]

    response = prep_response(scene_list)

    return response


def calc_urban_score(event, context):
    '''
    An AWS Lambda function that takes a scene and a geojson region and return
    the urban score in that region. This function also saves an image to S3.
    '''
    records = decode_records(event)

    outputs = []
    for record in records:
        args = parse_args(record)
        product_id = args['product_id']
        if 'geojson_s3_key' in args.keys():
            geojson = read_geojson_s3(args['geojson_s3_key'])
        elif 'geojson' in args.keys():
            geojson = (args['geojson'])

        image_swir = get_image(product_id, 'B6', geojson)
        image_nir =  get_image(product_id, 'B5', geojson)

        # Calculate the Normalized Difference Built-up Index
        ndbi = (image_swir-image_nir)/(image_swir+image_nir)

        # Calculate the urban score
        urban_score = np.nan_to_num(ndbi).sum() + np.count_nonzero(image_swir)

        date = get_landsat_date(product_id)

        json_obj = {'product_id': product_id,
                    'urban_score': urban_score,
                    'date': date}

        outputs.append(json_obj)

        fname = 'ndbi/%s_%s.png' % (date, datetime.now().strftime('%Y%m%d_%H%M%S'))
        plot_save_image_s3(ndbi, fname)

    response = prep_response(outputs)

    return response


