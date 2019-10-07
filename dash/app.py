import dash
import dash_core_components as dcc
import dash_html_components as html
import pandas as pd
import plotly.graph_objs as go
import boto3
from boto3.dynamodb.conditions import Key, Attr
from dash.dependencies import Input, Output, State
from scipy import signal

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

table_name = 'urban-development-score'
s3_bucket_name = 'urban-growth'

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)
server = app.server

# Read data from dynamoDB into a pandas DataFrame
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(table_name)

# Main layout of the page
app.layout = html.Div(children=[
    html.H2(id='header', children='Urban Growth'),
    html.Div(id='city-selector', children=[
        # Dropdown menu for selected cities
        dcc.Dropdown(
            id='city-dropdown',
            options=[
                {'label': 'Seattle', 'value': '20191003174728'},
                {'label': 'New York', 'value': '20191004211755'},
                {'label': 'San Francisco', 'value': 'SF'},
                {'label': 'Mukilteo', 'value': '20191003171955'},
                {'label': 'Upload GeoJSON', 'value': 'GEOJSON'}
            ],
            value='20191003174728'
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


@app.callback(Output("dev-score-vs-time", "figure"),
             [Input("button", "n_clicks")],
             [State("city-dropdown", "value")])
def update_figure(n_clicks, value):
    items = table.query(KeyConditionExpression=Key("query_id").eq(value))['Items']
    df = pd.DataFrame(items)
    figure={
        'data':[
            go.Scatter(
                x=pd.to_datetime(df['scene_date']),
                y=df['urban_score'],
                customdata=df['s3_key'],
                text=df['urban_score'],
                mode='markers',
                opacity=0.7,
                marker={
                    'size': 10,
                    'line': {'width': 0.5, 'color': 'white'}
                })]
        ,
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
    return figure


@app.callback(Output("upload", "style"),
             [Input("city-dropdown", "value")],
             [State("upload", "style")])
def show_upload_section(value, style):
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
    [State("city-dropdown", "options")])
def update_output(filename, file_content, options):
    if filename is None or file_content is None:
        return None, options
    s3 = boto3.client("s3")
    s3_key = "geojson/%s" % filename
    s3.put_object(Body=file_content, Bucket=s3_bucket_name, Key=s3_key)
    options.append({"label": s3_key, "value": s3_key})

    return s3_key, options


if __name__ == '__main__':
    app.run_server(host="localhost", debug=True)
