
import json
import numpy as np
import logging
from datetime import datetime
from tools import *
logger = logging.getLogger()
logger.setLevel(logging.INFO)


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
        geojson_s3_key = args['geojson_s3_key']
        geojson = get_geojson(args)

        try:
            # Short-wave Infrared - Band 6
            image_swir = get_image(product_id, 'B6', geojson)
            # Near Infrared - Band 5
            image_nir =  get_image(product_id, 'B5', geojson)
        except ValueError:
            # mask region does not overlap with raster image
            logger.error('Encountered error in %s, removing scenes...', product_id)
            db_response = decrease_counter(geojson_s3_key)
            return db_response

        # Calculate the Normalized Difference Built-up Index
        ndbi = (image_swir-image_nir)/(image_swir+image_nir)

        # Calculate the urban score
        n_pixels = (image_swir>0).sum()
        urban_score = ndbi.sum() / n_pixels + 1.0
        urban_score = np.nan_to_num(urban_score)

        date_wrs = get_landsat_date_wrs(product_id)

        # Plot the image
        fname = 'ndbi/%s_%s.png' % (query_id, date_wrs)

        key = {"query_id":       {"S": str(query_id)},
               "scene_date_wrs": {"S": str(date_wrs)}}
        # Item to be updated in database
        attr_values = {":urban_score": {"N": str(urban_score)},
                       ":n_pixels":    {"N": str(n_pixels)},
                       ":s3_key":      {"S": str(fname)}
                      }

        outputs.append(attr_values)

        logger.info('Updating DB: (%s, %s)', key, attr_values)
        db_response = db_update_item(key, attr_values)
        logger.info('DB response: %s', db_response)

        # Save image to S3
        s3_response = plot_save_image_s3(ndbi, fname)


    response = prep_response(outputs)

    return response


def get_scenes_send_queues(event, context):
    '''

    Input: args or args in the body of event
    args is a dictionary containing
        'geojson_s3_key': key (or the path) to geojson file on S3
        'cloud_cover_range': (min, max) cloud coverage
    '''
    args = parse_args(event)
    geojson_s3_key = args['geojson_s3_key']
    query_id = datetime.now().strftime('%Y%m%d%H%M%S')

    bbox = get_bbox(args)
    if 'cloud_cover_range' in args.keys():
        cloud_cover_range = args['cloud_cover_range']
    else:
        cloud_cover_range = (0, 10)
    items = search_scenes(bbox, cloud_cover=cloud_cover_range)
    logger.info('Found %3i scenes', len(items))

    for item in items:
        # Send job to SQS
        product_id = item.properties["landsat:product_id"]
        date_wrs = get_landsat_date_wrs(product_id)
        scene_datetime = item.properties["datetime"]

        job = {"query_id": query_id,
               "product_id": product_id,
               "geojson_s3_key": geojson_s3_key
              }
        logger.info('Sending message to SQS: %s', str(job))
        response = send_queue(job)

        # Put a place holder in database
        db_item = {"query_id":       {"S": str(query_id)},
                   "scene_date_wrs": {"S": str(date_wrs)},
                   "scene_datetime": {"S": str(scene_datetime)},
                   "product_id":     {"S": str(product_id)},
                   "urban_score":    {"N": str(0)},
                   "n_pixels":       {"N": str(0)},
                   "geojson_s3_key": {"S": str(geojson_s3_key)},
                   "s3_key":         {"S": 'na'}
                  }
        db_response = db_put_item(db_item)

    # Update the regions table
    db_item = {"geojson_s3_key": {"S": str(geojson_s3_key)},
               "query_id": {"S": str(query_id)},
               "number_of_scenes": {"N": str(len(items))}
              }
    db_response = db_put_item(db_item, table_name='regions')

    output = {"query_id": query_id,
              "geojson_s3_key": geojson_s3_key,
              "cloud_cover_range": cloud_cover_range,
              "number_of_scenes": len(items)
             }
    response = prep_response(output)

    return response
