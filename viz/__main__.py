import logging
import urllib.request
import os

import dash
import dash_core_components as dcc
import dash_html_components as html
import pandas as pd
import numpy as np
import googlemaps
from plotly.offline import iplot
from plotly.graph_objs import Scattermapbox, Layout, Figure

# read these from env variables
GEOCODE_API_KEY = os.environ['GEOCODE_API_KEY']
MAPBOX_ACCESS_TOKEN = os.environ['MAPBOX_ACCESS_TOKEN']
URL = 'https://data.cityofnewyork.us/api/views/43nn-pn8j/rows.csv?accessType=DOWNLOAD'
ADDRESS_COLUMNS = ['DBA', 'BUILDING', 'STREET', 'BORO', 'ZIPCODE']

gmaps = googlemaps.Client(key=GEOCODE_API_KEY)

logger = logging.getLogger('__main__')


def read_data_set():
    """ Download the DOHMH New York City Restaurant Inspection Results

        Returns
        -------
        df: DataFrame
            dataframe containing NYC restaurant inspection results
        cuisines: array
            list of all cuisine types in the data set
    """
    with urllib.request.urlopen(URL) as response:
        df = pd.read_csv(response)
    cuisines = df['CUISINE DESCRIPTION'].unique()
    return df, cuisines


# ideally this would be called on server start
# there would also be a background job to
# periodically download a new copy of the
# data file
DF, CUISINES = read_data_set()


def get_dropdown_labels(cuisines):
    """ Drop-down labels for selecting cuisine

        Parameters
        ----------
        cuisines: array
            list of cuisines

        Returns
        -------
        list of dict
    """
    return [{'label': cuisine, 'value': cuisine}
            for cuisine in cuisines]


def get_top_N(restos, cuisine_type='Thai', N=10):
    """ Return the top {N} cleanest {cuisine_type}
        restaurants

        Parameters
        ----------
        restos: DataFrame
            contains NYC restaurant inspection results
        cuisine_type: str
            type of cuisine to search for
        N: int
            top N restaurants to return

        Returns
        -------
        top_ten: DataFrame
            restos filtered for top {N} cleanest {cuisine_type}
            restaurants
    """
    candidates = (restos
                  .loc[((restos.GRADE == 'A') | (restos.GRADE == 'B')) &
                       (restos['CUISINE DESCRIPTION'] == cuisine_type)]
                  .sort_values(by='GRADE DATE', ascending=False)
                  # only keep most recent grading
                  .drop_duplicates(subset=['CAMIS'], keep='first')
                  )
    top_ten = (candidates
               .sort_values(by='SCORE', ascending=True)
               .iloc[:N]
               )
    return top_ten


def create_full_address(resto):
    """ Convert restaurant address data in different columns
        into a single string containing the address

        Parameters
        ----------
        resto: Series
            row of dataframe containing NYC restaurant inspection results

        Returns
        -------
        address: str
            full address as single string
    """
    address = (f"{resto['BUILDING']} {resto['STREET']}, "
               f"{resto['BORO']} {int(resto['ZIPCODE'])}")
    return address


def get_lat_lon(resto):
    """ Retrieve lat, lon of restaurant address

        Parameters
        ----------
        resto: Series
            row of dataframe containing NYC restaurant inspection results

        Returns
        -------
        dict
            containing name of restaurant and lat, lon location
    """
    address = create_full_address(resto)
    logger.info(f'querying for address {address}')
    results = gmaps.geocode(address)

    if len(results) > 0:
        lat = results[0].get('geometry', {}).get('location', {}).get('lat')
        lon = results[0].get('geometry', {}).get('location', {}).get('lng')
        logger.info(f'lat, lon = {lat}, {lon}')
        return {'name': resto['DBA'],
                'lat': lat,
                'lon': lon}
    else:
        logger.info(f'no results returned for {resto["DBA"]}')
        return {'name': resto['DBA'],
                'lat': np.nan,
                'lon': np.nan}


def find_lat_lon(top_ten):
    """ Find the lat, lon of all the restaurants in
        the top ten list

        Parameters
        ----------
        top_ten: DataFrame
            contains NYC restaurant inspection results
            for top ten cleanest restaurants

        Returns
        -------
        lat_lons: Series of dict
            name, lat, lon of each restaurant in the top_ten
            dataframe
    """
    lat_lons = top_ten[
        ADDRESS_COLUMNS
        ].apply(get_lat_lon, axis=1)
    return lat_lons


def plot_map(restos, cuisine_type='Thai'):
    """ Visualise restaurants on a map of NYC

        Parameters
        ----------
        restos: DataFrame
            contains NYC restaurant inspection results
        cuisine_type: str
            type of cuisine to search for

        Returns
        -------
        fig : plotly.Figure
    """
    top_ten = get_top_N(restos, cuisine_type=cuisine_type)
    lat_lons = find_lat_lon(top_ten)

    nyc_central_lat = 40.7128
    nyc_central_lon = -73.9

    data = [
        Scattermapbox(
            lon=[lat_lon['lon'] for lat_lon in lat_lons.values],
            lat=[lat_lon['lat'] for lat_lon in lat_lons.values],
            text=[lat_lon['name'] for lat_lon in lat_lons.values],
            mode='markers+text',
            showlegend=False,
            hoverinfo='text',
            textposition='top center',
            marker=dict(symbol='star',
                        size=10),
        )
    ]

    layers = [dict(sourcetype='geojson',
                   type='fill',
                   color='rgba(163,22,19,0.8)'
                   )
              ]

    layout = Layout(title='',
                    height=800,
                    width=600,
                    autosize=True,
                    hovermode='closest',
                    mapbox=dict(layers=layers,
                                accesstoken=MAPBOX_ACCESS_TOKEN,
                                bearing=0,
                                center=dict(lat=nyc_central_lat,
                                            lon=nyc_central_lon),
                                pitch=0,
                                zoom=10,
                                style='light'
                                ),
                    )

    fig = Figure(layout=layout, data=data)
    iplot(fig, validate=False)

    return fig


def generate_table(dataframe, max_rows=10):
    """ Generate HTML table from dataframe

        Parameters
        ----------
        dataframe: DataFrame
            data to display
        max_rows: int
            maximum number of rows to display

        Returns
        -------
        html.Table
    """
    return html.Table(
        id='output-table',
        children=
        # Header
        [html.Tr([html.Th(col) for col in dataframe.columns])] +

        # Body
        [html.Tr([
            html.Td(dataframe.iloc[i][col]) for col in dataframe.columns
        ]) for i in range(min(len(dataframe), max_rows))]
    )


external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

app = dash.Dash(__name__, external_stylesheets=external_stylesheets)

colors = {
    'background': '#111111',
    'text': '#7FDBFF'
}

app.layout = html.Div(children=[

    html.H1(children='Where to eat tonight!',
            style={'textAlign': 'center',
                   'color': colors['text']}),

    dcc.Dropdown(
        id='cuisine-dropdown',
        options=get_dropdown_labels(CUISINES),
        value='Thai'
    ), html.Div(id='output-container'),

    dcc.Graph(
        id='restaurant-map',
    ),

    html.H4(id='output-title'),

    generate_table(get_top_N(DF)[ADDRESS_COLUMNS]),

])


@app.callback(
    dash.dependencies.Output('output-container', 'children'),
    [dash.dependencies.Input('cuisine-dropdown', 'value')])
def print_selection(value):
    return f'You have selected "{value}" restaurants'


@app.callback(
    dash.dependencies.Output('restaurant-map', 'figure'),
    [dash.dependencies.Input('cuisine-dropdown', 'value')])
def plot_selection(value):
    return plot_map(DF, cuisine_type=value)


@app.callback(
    dash.dependencies.Output('output-title', 'children'),
    [dash.dependencies.Input('cuisine-dropdown', 'value')])
def print_selection(value):
    return f'Top Ten cleanest {value} restaurants'


@app.callback(
    dash.dependencies.Output('output-table', 'children'),
    [dash.dependencies.Input('cuisine-dropdown', 'value')])
def print_table(value):
    return generate_table(get_top_N(DF, cuisine_type=value)[ADDRESS_COLUMNS])


if __name__ == '__main__':
    app.run_server(debug=True)

