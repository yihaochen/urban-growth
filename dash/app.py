import pandas as pd
import json
import base64
import dash
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
import boto3
from boto3.dynamodb.conditions import Key, Attr
from dash.dependencies import Input, Output, State
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

table_name = 'urban-development-score'
s3_bucket_name = 'urban-growth'
lambda_function_name = 'urban-growth-test-get-scenes-send-queues'

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
server = app.server

# Read data from dynamoDB into a pandas DataFrame
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(table_name)
regions_table = dynamodb.Table('regions')

# A list for indicating the Lambda function is running
running = []

# Main layout of the page
app.layout = html.Div(children=[
    html.H2(id='header', children='Urban Growth'),
    html.Div(id='city-selector', children=[
        # Dropdown menu for selected cities
        dcc.Dropdown(
            id='city-dropdown',
            options=[
                {'label': 'Seattle', 'value': 'geojson/seattle.geojson'},
                {'label': 'New York', 'value': 'geojson/new-york-city.geojson'},
                {'label': 'San Francisco', 'value': 'geojson/san-francisco.geojson'},
                {'label': 'Mukilteo', 'value': 'geojson/mukilteo_silver_firs.geojson'},
                {'label': 'Upload GeoJSON', 'value': 'GEOJSON'}
            ],
            value='geojson/seattle.geojson'
        ),
        # Upload user's own GeoJSON file, default hidden
        dcc.Upload(
            id='upload',
            children=html.Div([
                'Drag and Drop or ',
                html.A('Select a File')
            ]),
            style={'display': 'none'},
            # Do not allow multiple files to be uploaded
            multiple=False
        ),
        # Submit button
        html.Button('Submit', id='button'),
        html.P('# of scenes:', id='scenes-counter', style={'float': 'right'}),
        # Interval counter
        dcc.Interval(
            id='interval',
            interval=1*1000, # in milliseconds
            n_intervals=0,
            disabled=True   # disabled at page load
        )
    ]),
    html.Hr(),
    dcc.Graph(
        id='dev-score-vs-time',
        className='column',
        style={'width': 600},
    ),
        html.Img(id='ndbi-image',
            className='column',
            style={'width': 500},
        )
],
)


@app.callback(Output("ndbi-image", "src"),
             [Input("dev-score-vs-time", "hoverData")],
             [State("ndbi-image", "src")])
def update_image_src(hover_data, old_src):
    if hover_data:
        date = hover_data["points"][0]["x"]
        if date[5:7] in ['06', '07', '08']:
            key = hover_data["points"][0]["customdata"]
            src = "https://{}.s3-us-west-2.amazonaws.com/{}".format(s3_bucket_name,key)
            return src
        else:
            return old_src
    else:
        return old_src


@app.callback([Output("dev-score-vs-time", "figure"),
               Output("interval", "disabled"),
               Output("scenes-counter", "children")],
              [Input("button", "n_clicks"),
               Input("interval", "n_intervals")],
              [State("city-dropdown", "value")])
def update_figure(n_clicks, n_intervals, value):
    logger.info('[update_figure] (nclicks, n_intervals, value)', n_clicks, n_intervals, value)

    # Basic layout for the figure
    figure={
        'layout': go.Layout(
            xaxis={'type': 'date', 'title': 'Date',
                   'showspikes': True,
                   'spikecolor': 'black',
                   'spikemode': 'across+marker',
                   'spikesnap': 'cursor'},
            yaxis={'title': 'Developement Score',
                   'range': [0.8, 1.1]},
            margin={'l': 50, 'b': 80, 't': 10, 'r': 10},
            legend={'x': 0, 'y': 1},
            hovermode='x',
            spikedistance=-1,
            #xaxis_rangeslider_visible=True
        )
    }

    region_query = regions_table.query(KeyConditionExpression=Key("geojson_s3_key").eq(value))
    # Call the lambda function if the geojson_s3_key is not in the query_info
    if region_query["ScannedCount"] < 1:
        if value in running:
            # Lambda is running. Do not invoke again
            return figure, False, '# of scenes: '
        func = boto3.client("lambda")
        payload = {"geojson_s3_key": value,
                   "cloud_cover_range": [0, 50]}
        response = func.invoke(FunctionName=lambda_function_name,
                               Payload=json.dumps(payload),
                               InvocationType='Event')
        running.append(value)

        logger.info("response: %s", str(response))

        return figure, False, '# of scenes: '
    else:
        region_item = region_query["Items"][0]
        query_id = region_item["query_id"]
        n_scenes = region_item["number_of_scenes"]

    items = table.query(KeyConditionExpression=Key("query_id").eq(query_id))["Items"]
    df = pd.DataFrame(items)

    n_done = (df['urban_score'] > 0).sum()
    logger.info('# scenes done/all:', n_done, n_scenes)
    interval_disabled = n_done >= n_scenes
    counter_text = '# of scenes: %3i/%3i' % (n_done, n_scenes)

    if n_done == 0:
        return figure, False, counter_text
    else:
        df_done = df[df['urban_score'] > 0]
        scene_datetime = pd.to_datetime(df_done['scene_datetime'])
        #mask = scene_datetime.dt.month.isin([6,7,8])
        mask = scene_datetime.dt.month > 0
        figure['data'] = [\
            go.Scatter(
                x=scene_datetime[mask],
                y=df_done[mask]['urban_score'],
                customdata=df_done[mask]['s3_key'],
                text=df_done[mask]['urban_score'],
                mode='markers',
                opacity=0.7,
                marker={
                    'size': 8,
                    'line': {'width': 0.5, 'color': 'white'}}
            )
        ]
    return figure, interval_disabled, counter_text


@app.callback(Output("upload", "style"),
             [Input("city-dropdown", "value")],
             [State("upload", "style")])
def toggle_upload_section(value, style):
    if value == 'GEOJSON':
        style={
            'width': '100%',
            'height': '60px',
            'lineHeight': '60px',
            'borderWidth': '1px',
            'borderStyle': 'dashed',
            'borderRadius': '5px',
            'textAlign': 'center',
            'margin': '10px',
            'display': 'block'
        }
    else:
        style['display'] = 'none'
    return style


@app.callback(
    [Output("city-dropdown", "value"), Output("city-dropdown", "options")],
    [Input("upload", "filename"), Input("upload", "contents")],
    [State("city-dropdown", "value"), State("city-dropdown", "options")])
def update_dropdown_options(filename, file_content, value, options):
    if filename is None or file_content is None:
        return value, options
    s3 = boto3.client("s3")
    s3_key = "geojson/%s" % filename
    content_type, content_string = file_content.split(',')
    decoded = base64.b64decode(content_string)
    s3.put_object(Body=decoded.decode('utf-8'), Bucket=s3_bucket_name, Key=s3_key)
    options.append({"label": s3_key, "value": s3_key})

    return s3_key, options


if __name__ == '__main__':
    app.run_server(host="localhost", debug=True)
