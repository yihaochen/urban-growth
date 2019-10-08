from handler import get_scenes_send_queues, get_scenes, calc_urban_score, read_json

def test_calc_urban_score():
    print('\nTesting calc_urban_score')
    print('\t- Using geojson_s3_key...')
    print(calc_urban_score({"query_id": 0, "product_id": "LC08_L1TP_047027_20190828_20190903_01_T1", "geojson_s3_key": "geojson/seattle-city-limits.geojson"}, None))

    print('\t- Using geojson...')
    print(calc_urban_score({"query_id": 0, "product_id": "LC08_L1TP_047027_20190828_20190903_01_T1", "geojson": read_json("seattle-city-limits.geojson")}, None))


def test_get_scenes():
    print('\nTesting get_scenes')
    print('\t- Using bbox...')
    print(get_scenes({"bbox": [-122.34, 47.6, -122.33, 47.61]}, None))
    print('\t- Using geojson...')
    print(get_scenes(read_json("seattle-city-limits.geojson"), None))


def test_get_scenes_send_queues():
    print('\nTesting get_scenes_send_queues')
    print(get_scenes_send_queues({"geojson_s3_key": "geojson/seattle.geojson"}, None))


def main():
    test_get_scenes_send_queues()
    test_calc_urban_score()
    test_get_scenes()


if __name__ == '__main__':
    main()
