## Project Idea/Business Value

This is an Insight Data Engineering project. The goal is to construct a data
pipeline to extract analytics from time-series satellite images. I implement
the pipeline on AWS with the serverless Lambda service.

## Tech Stack

Development and deployment: Docker, serverless

AWS: S3, Lambda, SQS, DynamoDB

Frontend: Dash

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

A web interface that allows user to specify a region and returns historical
urban region graph.

## Stretch Goals

1. A web-based map browser that allows user to select a rectangular region in
   the map.
2. Allow user to select a city, identify the region of the city, and use the
   region for image selection

## Instructions

### Requierement
  - AWS Account
  - awscli
  - Docker
  - npm (serverless)

### Fill in AWS credential

```
cp sample.env .env

vi .env
```
Put your AWS access key id and secret access key in `.env`.

### Create and deploy

```
make build

npm install -g serverless

sls deploy
```

---
### Reference

[simple-rio-lambda](https://github.com/vincentsarago/simple-rio-lambda/)
