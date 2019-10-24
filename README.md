## Project Idea/Business Value

This is an Insight Data Engineering project. The objective is to construct a
data pipeline to extract analytics from time-series satellite images. I
implement the pipeline on AWS with the serverless Lambda service to get
flexible performance scaling and cost efficiency.

## Tech Stack

Development and deployment: Docker, serverless

AWS: S3, Lambda, SQS, DynamoDB

Frontend: Dash

## Data Source

[Landsat-8 dataset on AWS S3](https://registry.opendata.aws/landsat-8/)
<!-- [Sentiel-2 dataset hosted on Amazon S3](https://registry.opendata.aws/sentinel-2/) -->

## Engineering Challenge

- Lambda has strict source code size limit. How do we include all dependencies
  of the image processing in the package?
- If the region spans to more than 1 scenes, how to combine them?
- How to avoid clouded images and access the quality of each scene?

## MVP

A web interface that allows user to specify a region (by a geojson file) and
returns historical urban region graph.

## Deployment Instructions

### AWS Lambda functions

#### Requierement
  - AWS Account
  - awscli
  - Docker
  - npm (serverless)

#### Fill in AWS credential

```
cp sample.env .env

vi .env
```
Put your AWS access key id and secret access key in `.env`.

#### Create and deploy

```
make build

npm install -g serverless

sls deploy
```

### Frontend with Dash

#### Set up an EC2 instance and install python3

#### Use nginx and gunicorn for web hosting (optinal)


---
## Reference

[simple-rio-lambda](https://github.com/vincentsarago/simple-rio-lambda/)
