
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
	docker exec -it lambda python3 tests.py

	docker stop lambda
	docker rm lambda

clean:
	docker stop lambda
	docker rm lambda
