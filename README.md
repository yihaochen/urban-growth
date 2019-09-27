## Project Idea/Business Value

Provide an interface to extract analytics from time-series satellite images. 

## Tech Stack

AWS: S3, Lambda, API Gateway; Flask

## Data Source

[Landsat-8 dataset on AWS S3](https://registry.opendata.aws/landsat-8/)
<!-- [Sentiel-2 dataset hosted on Amazon S3](https://registry.opendata.aws/sentinel-2/) -->

## Engineering Challenge

- How to process images in parallel?
- If the region spans to more than 1 scenes, how to combine them?
- How to mask city region in satellite images?
- How to downsample images when the region is large?
- How to avoid clouded images and access the quality of each scene?

## MVP

A web interface that allows user to specify a rectangular region and returns historical urban region graph.

### Requierement
  - AWS Account
  - awscli
  - Docker
  - npm (serverless)

### Create and deploy

```
make build

npm install -g serverless

sls deploy
```

## Stretch Goals

1. A web-based map browser that allows user to select a rectangular region in the map
2. Allow user to select a city, identify the region of the city, and use the region for image selection
