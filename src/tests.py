from handler import get_scenes_send_queues, calc_urban_score

def test_calc_urban_score():
    print('\nTesting calc_urban_score')
    print('\t- Using geojson_s3_key...')
    print(calc_urban_score({"query_id": 0, "product_id": "LC08_L1TP_047027_20190828_20190903_01_T1", "geojson_s3_key": "geojson/seattle.geojson"}, None))


def test_get_scenes_send_queues():
    print('\nTesting get_scenes_send_queues')
    print(get_scenes_send_queues({"geojson_s3_key": "geojson/seattle.geojson"}, None))


def main():
    test_calc_urban_score()
    test_get_scenes_send_queues()


if __name__ == '__main__':
    main()
