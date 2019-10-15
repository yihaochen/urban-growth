import pandas as pd
import numpy as np
import json
import base64
import dash
import dash_daq as daq
import dash_core_components as dcc
import dash_html_components as html
import plotly.graph_objs as go
import boto3
from boto3.dynamodb.conditions import Key, Attr
from dash.dependencies import Input, Output, State
import logging

logger = logging.getLogger()
logger.addHandler(logging.StreamHandler())
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

# A boolean variable to indicate first update of the figure
first_update = True

# Main layout of the page
app.layout = html.Div(children=[
    html.H4(id='header', children='Urban Growth'),
    html.Div(id='city-selector', style={'padding':'0 10px 10px 10px'}, children=[
        # Dropdown menu for selected cities
        dcc.Dropdown(
            id='city-dropdown',
            options=[
                {'label': 'Seattle, WA', 'value': 'geojson/seattle.geojson'},
                {'label': 'New York, NY', 'value': 'geojson/new-york-city.geojson'},
                {'label': 'San Francisco, CA', 'value': 'geojson/san-francisco.geojson'},
                {'label': 'Chicago, IL', 'value': 'geojson/chicago.geojson'},
                {'label': 'Madison, WI', 'value': 'geojson/madison.geojson'},
#                {'label': 'Mukilteo', 'value': 'geojson/mukilteo_silver_firs.geojson'},
                {'label': 'northwest Enterprise, NV', 'value': 'geojson/enterprise_nw_box.geojson'},
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
        )
    ]),
    html.Div(id='submit-info', style={'padding':'0 10px 30px 10px'}, children=[
        # Submit button
        html.Button('Submit', id='button', style={'font-size': '14px', 'height': '48px'}),
        # Counter for the number of scenes and toggle for images
        html.Div(id='text-and-check-box', style={'float': 'right', 'text-align': 'right'}, children=[
            html.P('# of scenes:', id='scenes-counter'),
            daq.BooleanSwitch(
                id='summer-only',
                on=True,
                label='Hover summer images only',
                labelPosition='right'
            ),
        ]),
        # Interval counter
        dcc.Interval(
            id='interval',
            interval=1*1000, # in milliseconds
            n_intervals=0,
            disabled=True   # disabled at page load
        ),
    ]),
    #html.Hr(),
    html.Div(id='figure-div', style={'width': 1080}, className='column', children=[
        dcc.Graph(
            id='dev-score-vs-time',
            className='column',
            style={'width': 600},
        ),
        html.Img(id='ndbi-image',
            className='column',
            style={'width': 'auto', 'max-width': 400, 'height': 'auto', 'max-height': 500},
        )
    ]),
],
)


@app.callback(Output("ndbi-image", "src"),
             [Input("dev-score-vs-time", "hoverData")],
             [State("ndbi-image", "src"),
              State("summer-only", "on")])
def update_image_src(hover_data, old_src, summer_only):
    if hover_data:
        if "curveNumber" not in hover_data["points"][0] and summer_only:
            return old_src
        curveNumber = hover_data["points"][0]["curveNumber"]
        if curveNumber == 4 or not summer_only:
            key = hover_data["points"][0]["customdata"]
            src = "https://{}.s3-us-west-2.amazonaws.com/{}".format(s3_bucket_name,key)
            return src
        else:
            return old_src
    else:
        return ''


@app.callback([Output("dev-score-vs-time", "figure"),
               Output("interval", "disabled"),
               Output("scenes-counter", "children"),
               Output("dev-score-vs-time", "hoverData")],
              [Input("button", "n_clicks"),
               Input("interval", "n_intervals")],
              [State("city-dropdown", "value"),
               State("dev-score-vs-time", "hoverData")])
def update_figure(n_clicks, n_intervals, value, hoverData):
    logger.info('[update_figure] (n_clicks, n_intervals, value) = (%s, %s, %s)', str(n_clicks), str(n_intervals), str(value))

    # Basic layout for the figure
    figure={
        'layout': go.Layout(
            xaxis={'type': 'date', 'title': 'Date',
                   'showspikes': True,
                   'spikecolor': 'black',
                   'spikemode': 'across+marker',
                   'spikesnap': 'cursor'},
            yaxis={'title': 'Developement Score',
                   'range': [0.87, 1.06]},
            margin={'l': 50, 'b': 60, 't': 10, 'r': 10},
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
            return figure, False, '# of scenes: ', hoverData
        func = boto3.client("lambda")
        payload = {"geojson_s3_key": value,
                   "cloud_cover_range": [0, 80]}
        response = func.invoke(FunctionName=lambda_function_name,
                               Payload=json.dumps(payload),
                               InvocationType='Event')
        running.append(value)

        logger.info("response: %s", str(response))

        return figure, False, '# of scenes: ', None
    else:
        region_item = region_query["Items"][0]
        query_id = region_item["query_id"]
        n_scenes = region_item["number_of_scenes"]

    items = table.query(KeyConditionExpression=Key("query_id").eq(query_id))["Items"]
    df = pd.DataFrame(items)

    n_done = (df['urban_score'] > 0).sum()
    logger.info('# scenes done/all: %3i/%3i', n_done, n_scenes)
    interval_disabled = n_done >= n_scenes
    counter_text = '# of scenes: %3i/%3i' % (n_done, n_scenes)

    if n_done == 0:
        #print('n_done', n_done)
        logger.info('n_done: %i', n_done)
        return figure, False, counter_text, None
    else:
        df_done = df[df['urban_score'] > 0]
        df_done['scene_datetime'] = pd.to_datetime(df_done['scene_datetime'])
        df_done.set_index('scene_datetime', inplace=True)

        fields = ['urban_score', 'valid_percent']
        for f in fields:
            df_done[f] = pd.to_numeric(df_done[f])

        # Remove outliers
        mean = df_done['urban_score'].mean()
        std =  df_done['urban_score'].std()
        df_done = df_done.mask((df_done['urban_score'] - mean).abs() > 2*std).dropna()
        print('mean:', mean, 'std:', std)

        # Summer mask
        mean = df_done['urban_score'].mean()
        std =  df_done['urban_score'].std()
        #mask = df_done['urban_score'] < mean - 0.75*std
        mask = np.logical_and(df_done.index.month.isin([5,6,7,8]), df_done['urban_score'] < mean-0.5*std)

        # Resample the data for filled region
        oidx = df_done.index
        nidx = pd.date_range(oidx.min(), oidx.max(), freq='1M')
        res = df_done.rolling('90D', closed='both').mean().reindex(oidx.union(nidx)).interpolate('linear').drop(oidx)
        #print(res)

        # Error from std
        err = df_done['urban_score'].std()/np.sqrt(df_done['valid_percent'])
        err = err.reindex(oidx.union(nidx)).interpolate('linear').drop(oidx)
        # Drawing the figure
        figure['data'] = [
            go.Scatter(
                x=res.index,
                y=res['urban_score']+err,
                showlegend=False,
                hoverinfo='skip',
                mode='lines', line_width=0),
            go.Scatter(
                x=res.index,
                y=res['urban_score']-err,
                showlegend=False,
                hoverinfo='skip',
                fill='tonexty', # fill area between trace0 and trace1
                fillcolor='rgba(192,192,192,0.5)',
                mode='lines', line_width=0),
            go.Scatter(
                x=res.index,
                y=res['urban_score'].ewm(span=48, min_periods=9).mean(),
                name='exponential moving average',
                hoverinfo='skip',
                line_color='#ff7f0e',
                mode='lines', line_width=2),
            # Non-summer points
            go.Scatter(
                x=df_done[~mask].index,
                y=df_done[~mask]['urban_score'],
                customdata=df_done[~mask]['s3_key'],
                name='non-summer',
                text=df_done[~mask]['valid_percent']*100,
                hovertemplate='Dev Score: %{y:.4f}<br>Valid pixels: %{text:.1f} %',
                mode='markers',
                opacity=0.5,
                marker_color='#0c600c',
                marker={'size': 6}
            ),
            # Summer points
            go.Scatter(
                x=df_done[mask].index,
                y=df_done[mask]['urban_score'],
                customdata=df_done[mask]['s3_key'],
                name='summer',
                text=df_done[mask]['valid_percent']*100,
                hovertemplate='Dev Score: %{y:.4f}<br>Valid pixels: %{text:.1f} %',
                mode='markers',
                opacity=0.7,
                marker_color='#2ca02c',
                marker={
                    'size': 8,
                    'line': {'width': 0.5, 'color': 'white'}}
            ),
        ]
        global first_update
        if first_update and len(df_done[mask].index)>0:
            hover_update = {"points":
                    [{"x": df_done[mask].index[0],
                      "curveNumber": 4,
                      "customdata": df_done[mask]['s3_key'].iloc[0]}]}
            first_update = False
        else:
            hover_update = hoverData
    return figure, interval_disabled, counter_text, hover_update


@app.callback(Output("upload", "style"),
             [Input("city-dropdown", "value")],
             [State("upload", "style")])
def toggle_upload_section(value, style):
    global first_update
    first_update = True
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
    app.run_server(host="0.0.0.0", debug=True)
