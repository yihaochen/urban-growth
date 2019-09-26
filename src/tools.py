
import rasterio
import json
import numpy as np
import re
import os
from rasterio.mask import mask

def landsat_parse_scene_id(sceneid):
    '''
    Author @perrygeo - http://www.perrygeo.com

    parse scene id
    '''

    if not re.match('^(L[COTEM]8\d{6}\d{7}[A-Z]{3}\d{2})|(L[COTEM]08_L\d{1}[A-Z]{2}_\d{6}_\d{8}_\d{8}_\d{2}_(T1|T2|RT))$', sceneid):
        raise ValueError(f'Could not match {sceneid}')

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
        match = re.match(pattern, sceneid, re.IGNORECASE)
        if match:
            meta = match.groupdict()
            break

    if not meta:
        raise ValueError(f'Could not match {sceneid}')

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
        sceneid,
        sceneid)

    meta['scene'] = sceneid

    return meta


def get_landsat_s3_url(sceneid, band):
    meta = landsat_parse_scene_id(sceneid)
    meta['band'] = band
    s = 's3://landsat-pds/{key}_{band:2}.TIF'
    url = s.format(**meta)
    return url


def parse_args(event):
    # For API calls, the input arguments are in "body"
    if 'body' in event.keys():
        args = json.loads(event['body'])
    else:
        args = event
    return args


def prep_response(output):

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


def get_bbox_geojson(geojson):
    c1_min, c1_max = 180, -180
    c2_min, c2_max = 90, -90
    for f in geojson['features']:
        c = f["geometry"]["coordinates"][0]
        c1_min = min([x[0] for x in c]+[c1_min]) # first coordinate
        c1_max = max([x[0] for x in c]+[c1_max])
        c2_min = min([x[1] for x in c]+[c2_min]) # second coordinate
        c2_max = max([x[1] for x in c]+[c2_max])
    bbox = [c1_min, c2_min, c1_max, c2_max]
    return bbox


def search_scenes(bbox, collection='landsat-8-l1', cloud_cover=(0,10)):
    search = Search(bbox=bbox,
                    query={'eo:cloud_cover': {'gt': cloud_cover[0],
                                              'lt': cloud_cover[1]},
                           'collection': {'eq': collection}
                          }
                   )
    return search.items()


def get_image(product_id, band, geojson):
    s3_url = get_landsat_s3_url(product_id, band)
    src = rasterio.open(s3_url)

    features = [rasterio.warp.transform_geom('EPSG:4326', src.crs, feature["geometry"])
                for feature in geojson['features']]

    image, transform = mask(src, features, crop=True, indexes=1)

    return image.astype(np.int16)
