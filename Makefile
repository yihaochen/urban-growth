
SHELL = /bin/bash

build:
	docker build --tag lambda:latest .
	docker run --name lambda -itd lambda:latest /bin/bash
	docker cp lambda:/tmp/package.zip package.zip
	docker stop lambda
	docker rm lambda

shell:
	docker build --tag lambda:latest .
	docker run --name docker  \
		--volume $(shell pwd)/:/local \
		--env-file ./.env \
		--rm -it lambda:latest bash

test: build
	docker run \
		--name lambda \
		--volume $(shell pwd)/:/local \
		--env-file ./.env \
		-itd \
		lambci/lambda:build-python3.6 bash

	docker exec -it lambda bash -c 'unzip -q /local/package.zip -d /var/task/'
	docker cp seattle-city-limits.geojson lambda:/var/task/
	docker exec -it lambda python3 -c 'from handler import calc_urban_score, read_json; print(calc_urban_score({"product_id": "LC08_L1TP_047027_20190828_20190903_01_T1", "date": "2019-08-28","geojson": read_json("seattle-city-limits.geojson")}, None))'

	docker exec -it lambda python3 -c 'from handler import get_scenes; print(get_scenes({"bbox": [-122.34, 47.6, -122.33, 47.61]}, None))'
	docker exec -it lambda python3 -c 'from handler import get_scenes, read_json; print(get_scenes(read_json("seattle-city-limits.geojson"), None))'

	docker stop lambda
	docker rm lambda

clean:
	docker stop lambda
	docker rm lambda
