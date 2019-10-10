
import rasterio
import json
import numpy as np
import matplotlib.pyplot as plt
import re
import os
import boto3
import base64
from satsearch import Search
from rasterio.mask import mask
from l8qa import qa

def landsat_parse_product_id(product_id):
    '''
    Parse Product ID

    The data are organized using a directory structure based on each scene’s
    path and row. For instance, the files for Landsat scene
    LC08_L1TP_139045_20170304_20170316_01_T1 are available in the following
    location:
    s3://landsat-pds/c1/L8/139/045/LC08_L1TP_139045_20170304_20170316_01_T1/

    The “c1” refers to Collection 1, the “L8” refers to Landsat 8, “139” refers
    to the scene’s path, “045” refers to the scene’s row, and the final
    directory matches the product’s identifier, which uses the following naming
    convention: LXSS_LLLL_PPPRRR_YYYYMMDD_yyymmdd_CC_TX, in which:

    L = Landsat
    X = Sensor
    SS = Satellite
    PPP = WRS path
    RRR = WRS row
    YYYYMMDD = Acquisition date
    yyyymmdd = Processing date
    CC = Collection number
    TX = Collection category

    ---

    Modified from code by @perrygeo - http://www.perrygeo.com

    '''

    if not re.match('^(L[COTEM]8\d{6}\d{7}[A-Z]{3}\d{2})|(L[COTEM]08_L\d{1}[A-Z]{2}_\d{6}_\d{8}_\d{8}_\d{2}_(T1|T2|RT))$', product_id):
        raise ValueError(f'Could not match {product_id}')

    precollection_pattern = (
        r'^L'
        r'(?P<sensor>\w{1})'
        r'(?P<satellite>\w{1})'
        r'(?P<path>[0-9]{3})'
        r'(?P<row>[0-9]{3})'
        r'(?P<acquisitionYear>[0-9]{4})'
        r'(?P<acquisitionJulianDay>[0-9]{3})'
        r'(?P<groundStationIdentifier>\w{3})'
        r'(?P<archiveVersion>[0-9]{2})$'
    )

    collection_pattern = (
        r'^L'
        r'(?P<sensor>\w{1})'
        r'(?P<satellite>\w{2})'
        r'_'
        r'(?P<processingCorrectionLevel>\w{4})'
        r'_'
        r'(?P<path>[0-9]{3})'
        r'(?P<row>[0-9]{3})'
        r'_'
        r'(?P<acquisitionYear>[0-9]{4})'
        r'(?P<acquisitionMonth>[0-9]{2})'
        r'(?P<acquisitionDay>[0-9]{2})'
        r'_'
        r'(?P<processingYear>[0-9]{4})'
        r'(?P<processingMonth>[0-9]{2})'
        r'(?P<processingDay>[0-9]{2})'
        r'_'
        r'(?P<collectionNumber>\w{2})'
        r'_'
        r'(?P<collectionCategory>\w{2})$'
    )

    meta = None
    for pattern in [collection_pattern, precollection_pattern]:
        match = re.match(pattern, product_id, re.IGNORECASE)
        if match:
            meta = match.groupdict()
            break

    if not meta:
        raise ValueError(f'Could not match {product_id}')

    if meta.get('acquisitionJulianDay'):
        date = datetime.datetime(int(meta['acquisitionYear']), 1, 1) \
            + datetime.timedelta(int(meta['acquisitionJulianDay']) - 1)

        meta['date'] = date.strftime('%Y-%m-%d')
    else:
        meta['date'] = f'{meta.get("acquisitionYear")}-{meta.get("acquisitionMonth")}-{meta.get("acquisitionDay")}'

    collection = meta.get('collectionNumber', '')
    if collection != '':
        collection = f'c{int(collection)}'

    meta['key'] = os.path.join(collection,
        'L8',
        meta['path'],
        meta['row'],
        product_id,
        product_id)

    meta['product_id'] = product_id

    return meta


def get_landsat_s3_url(product_id, band):
    '''
    Return the Landsat 8 image URL on S3.
    '''
    meta = landsat_parse_product_id(product_id)
    meta['band'] = band
    s = 's3://landsat-pds/{key}_{band:2}.TIF'
    url = s.format(**meta)
    return url


def get_landsat_date_wrs(product_id):
    '''
    Get the acquisition date and wrs from the product id using regex.
    '''
    pattern = 'L[COTEM]08_L\d{1}[A-Z]{2}_(\d{6})_(\d{8})_\d{8}_\d{2}_(T1|T2|RT)$'
    wrs, date = re.match(pattern, product_id).groups()[:2]
    return '%s_%s' % (date, wrs)


def parse_args(event):
    '''
    Parse event from API calls or directly pass the input.
    '''
    # For API calls, the input arguments are in "body"
    if 'body' in event.keys():
        return json.loads(event['body'])
    else:
        return event


def decode_records(event):
    if 'Records' not in event.keys():
        return [event]

    # SQS message and Kinesis stream contain 'Records' key
    records = []
    for record in event['Records']:
        if 'kinesis' in record.keys():
            # Kinesis data is base64 encoded so decode here
            records.append(json.loads(base64.b64decode(record['kinesis']['data'])))
        else:
            records.append(record)
    return records


def prep_response(output):
    '''
    Put the output dictionary into the body of an HTTP response.
    '''
    response =  {
                'statusCode': 200,
                'headers': {'Content-Type': 'text/JSON'},
                'body': json.dumps(output),
                'isBase64Encoded':  False
                }

    return response


def read_json(fname):
    with open(fname, "r") as f:
        return json.load(f)


def get_geojson(args):
    '''
    Read geojson from S3 or get geojson from the attribute.
    '''
    if 'geojson_s3_key' in args.keys():
        return read_geojson_s3(args['geojson_s3_key'])
    elif 'geojson' in args.keys():
        return (read_json(args['geojson']))
    else:
        raise KeyError("Cannot find 'geojson' or 'geojson_s3_key' in args")


def get_bbox_geojson(geojson):
    '''
    Get the bounding box of the geojson polygons or multipolygons.
    '''
    # This function assumes cartesian coordiantes, rather than Mercator
    # The boundaries of the box might not align with north-south or west-east

    c1_min, c1_max = 180, -180
    c2_min, c2_max = 90, -90
    for feature in geojson["features"]:
        # Single Polygon; coordinates[0] is the boundary; coordinates[1:] are holes
        if feature["geometry"]["type"] == "Polygon":
            cc = [feature["geometry"]["coordinates"][0]]
        # MultiPolygon; coordinates are list of polygons
        else:
            cc = []
            for pol in feature["geometry"]["coordinates"][:][0]:
                cc.append(pol)
        for c in cc:
            c1_min = min([x[0] for x in c]+[c1_min]) # first coordinate
            c1_max = max([x[0] for x in c]+[c1_max])
            c2_min = min([x[1] for x in c]+[c2_min]) # second coordinate
            c2_max = max([x[1] for x in c]+[c2_max])
    bbox = [c1_min, c2_min, c1_max, c2_max]
    return bbox


def get_bbox(args):
    if 'bbox' in args.keys():
        return args['bbox']
    else:
        geojson = get_geojson(args)
        return get_bbox_geojson(geojson)


def search_scenes(bbox, collection='landsat-8-l1', cloud_cover=(0,10)):
    search = Search(bbox=bbox,
                    query={'eo:cloud_cover': {'gt': cloud_cover[0],
                                              'lt': cloud_cover[1]},
                           'collection': {'eq': collection}
                          }
                   )
    return search.items()


def read_geojson_s3(geojson_key, bucket_name='urban-growth'):
    '''
    Read the geojson file on s3 using boto3.
    '''
    s3 = boto3.client('s3')
    content_dict = s3.get_object(Bucket=bucket_name, Key=geojson_key)
    file_content = content_dict['Body'].read().decode('utf-8')
    return json.loads(file_content)


def get_image(product_id, band, geojson):
    '''
    Get the cloud masked image (numpy.ma.MaskedArray) of the geojson
    regions.
    '''
    s3_url = get_landsat_s3_url(product_id, band)
    qa_url = get_landsat_s3_url(product_id, 'BQA')

    # Image of the requested band
    with rasterio.open(s3_url) as src:
        features = [rasterio.warp.transform_geom('EPSG:4326',
            src.crs, feature["geometry"]) for feature in geojson['features']]

        image, transform = mask(src, features, crop=True, indexes=1)

    # Quality control band for cloud mask
    with rasterio.open(qa_url) as qa_src:
        qa_image, transform = mask(qa_src, features, crop=True, indexes=1)
        cloud_mask = qa.cloud_confidence(qa_image) >= 2

    masked_image = np.ma.masked_array(image, mask=cloud_mask, dtype=np.int16)

    # Raise error if there are less than 50% unmasked pixels
    if (masked_image>0).sum() < 0.8*(image>0).sum():
        raise ValueError

    return masked_image


def plot_save_image_s3(image, fname, bucket_name='urban-growth'):
    '''
    Plot the image and upload the file to S3.
    '''
    s3 = boto3.client('s3')

    # Plot figure
    fig = plt.figure(figsize=(10, 10))
    plt.imshow(image, vmin=-0.3, vmax=0.0, cmap='PiYG_r', interpolation='nearest')
    plt.axis('off')
    plt.tight_layout()
    plt.savefig('/tmp/tmp.png', bbox_inches='tight', pad_inches=0)
    response = s3.upload_file('/tmp/tmp.png', bucket_name, fname, ExtraArgs={'ACL':'public-read'})

    return response


def db_put_item(obj, table_name='urban-development-score'):
    '''
    Put an item in the database.
    '''
    db = boto3.client('dynamodb')
    response = db.put_item(
            TableName=table_name,
            Item=obj)

    return response


def db_update_item(key, attr_values, table_name='urban-development-score'):
    '''
    Update the itme in the database.
    '''
    db = boto3.client('dynamodb')
    update_expression = "SET "+
                "urban_score = :urban_score, "+
                "n_pixels = :n_pixels, "+
                "s3_key = :s3_key"
    response = db.update_item(
            TableName=table_name,
            Key=key,
            UpdateExpression=update_expression,
            ExpressionAttributeValues=attr_values
    )


def decrease_counter(geojson_s3_key, table_name='regions'):
    '''
    Decrease the number of scenes.
    '''
    db = boto3.client('dynamodb')
    response = db.update_item(
            TableName=table_name,
            Key={
                'geojson_s3_key': {'S': geojson_s3_key}
            },
            UpdateExpression="set number_of_scenes = number_of_scenes - :val",
            ExpressionAttributeValues={
                ':val': {'N': '1'}
            },
            ReturnValues="UPDATED_NEW"
    )
    return response


sqs_url = 'https://us-west-2.queue.amazonaws.com/940900654266/landsat-scenes'

def send_queue(job, queue_url=sqs_url):
    '''
    Send the job to SQS queue.
    '''
    sqs = boto3.client('sqs')
    response = sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(job))

    return response
