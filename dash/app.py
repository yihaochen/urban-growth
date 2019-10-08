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
             [Input("dev-score-vs-time", "hoverData")])
def update_image(hover_data):
    if hover_data:
        key = hover_data["points"][0]["customdata"]
        src = "https://{}.s3-us-west-2.amazonaws.com/{}".format(s3_bucket_name,key)
        return src
    else:
        return None


@app.callback([Output("dev-score-vs-time", "figure"),
               Output("interval", "disabled"),
               Output("scenes-counter", "children")],
              [Input("button", "n_clicks"),
               Input("interval", "n_intervals")],
              [State("city-dropdown", "value")])
def update_figure(n_clicks, n_intervals, value):
    print(n_clicks, n_intervals, value)
    region_query = regions_table.query(KeyConditionExpression=Key("geojson_s3_key").eq(value))
    # Call the lambda function if the geojson_s3_key is not in the query_info
    if region_query["ScannedCount"] < 1:
        func = boto3.client("lambda")
        payload = {"geojson_s3_key": value,
                   "cloud_cover_range": (0, 5)}
        response = func.invoke(FunctionName=lambda_function_name,
                               Payload=json.dumps(payload))

        response = json.loads(response['Payload'].read())
        print("response:", response)
        body = json.loads(response['body'])
        query_id = body['query_id']
        n_scenes = body['number_of_scenes']
    else:
        region_item = region_query["Items"][0]
        query_id = region_item["query_id"]
        n_scenes = region_item["number_of_scenes"]

    items = table.query(KeyConditionExpression=Key("query_id").eq(query_id))["Items"]

    print(len(items), n_scenes)
    interval_disabled = len(items) >= n_scenes
    counter_text = '# of scenes: %3i/%3i' % (len(items), n_scenes)

    figure={
        'layout': go.Layout(
            xaxis={'type': 'date', 'title': 'Date',
                   'showspikes': True,
                   'spikecolor': 'black',
                   'spikemode': 'across+marker',
                   'spikesnap': 'cursor'},
            yaxis={'title': 'Developement Score'},
            margin={'l': 100, 'b': 10, 't': 10, 'r': 10},
            legend={'x': 0, 'y': 1},
            hovermode='x',
            spikedistance=-1,
            xaxis_rangeslider_visible=True
        )
    }
    if len(items) == 0:
        return figure, False, counter_text
    else:
        df = pd.DataFrame(items)
        figure['data'] = [\
            go.Scatter(
                x=pd.to_datetime(df['scene_date']),
                y=df['urban_score'],
                customdata=df['s3_key'],
                text=df['urban_score'],
                mode='markers',
                opacity=0.7,
                marker={
                    'size': 10,
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
