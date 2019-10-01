
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

    bbox = get_bbox(args)

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
    # Decode from SQS messages
    records = decode_records(event)

    outputs = []
    for record in records:
        # Parse args from body in record
        args = parse_args(record)

        query_id = args['query_id']
        product_id = args['product_id']
        geojson = get_geojson(args)

        # Short-wave Infrared - Band 6
        image_swir = get_image(product_id, 'B6', geojson)
        # Near Infrared - Band 5
        image_nir =  get_image(product_id, 'B5', geojson)

        # Calculate the Normalized Difference Built-up Index
        ndbi = (image_swir-image_nir)/(image_swir+image_nir)

        # Calculate the urban score
        urban_score = np.nan_to_num(ndbi).sum() + np.count_nonzero(image_swir)

        date = get_landsat_date(product_id)

        # Plot the image
        fname = 'ndbi/%s_%s.png' % (query_id, date)

        s3_response = plot_save_image_s3(ndbi, fname)

        # Item to be written to database
        db_item = {"query_id": {"S": str(query_id)},
                   "scene_date": {"S": str(date)},
                   "product_id": {"S": str(product_id)},
                   "urban_score": {"N": str(urban_score)},
                   "s3_key": {"S": str(fname)}
                  }

        outputs.append(db_item)

        db_response = update_db(db_item)

    response = prep_response(outputs)

    return response


def get_scenes_send_queues(event, context):
    '''
    '''
    args = parse_args(event)
    geojson_s3_key = args['geojson_s3_key']
    query_id = datetime.now().strftime('%Y%m%d%H%M%S')

    bbox = get_bbox(args)
    if 'cloud_cover_range' in args.keys():
        cloud_cover_range = args['cloud_cover_range']
    else:
        cloud_cover_range = (0, 5)
    items = search_scenes(bbox, cloud_cover=cloud_cover_range)
    print('Found %3i scenes' % len(items))

    responses = []

    for item in items:
        job = {"query_id": query_id,
               "product_id": item.properties["landsat:product_id"],
               "geojson_s3_key": geojson_s3_key
              }
        response = send_queue(job)
        responses.append(response)

    return responses
