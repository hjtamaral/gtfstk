"""
Functions useful across modules.
"""
import datetime as dt
from typing import Optional, Dict, List, Union, Callable

import pandas as pd
from pandas import DataFrame
import numpy as np
from shapely.geometry import LineString, Point
from shapely.ops import transform
import utm
import json2table as j2t

from . import constants as cs


def datestr_to_date(
    x: Union[dt.date, str],
    format_str: str = "%Y%m%d",
    *,
    inverse: bool = False,
) -> Union[str, dt.date]:
    """
    Given a string ``x`` representing a date in the given format,
    convert it to a Datetime Date object and return the result.
    If ``inverse``, then assume that ``x`` is a date object and return
    its corresponding string in the given format.
    """
    if x is None:
        return None
    if not inverse:
        result = dt.datetime.strptime(x, format_str).date()
    else:
        result = x.strftime(format_str)
    return result


def timestr_to_seconds(
    x: Union[dt.date, str], *, inverse: bool = False, mod24: bool = False
) -> int:
    """
    Given an HH:MM:SS time string ``x``, return the number of seconds
    past midnight that it represents.
    In keeping with GTFS standards, the hours entry may be greater than
    23.
    If ``mod24``, then return the number of seconds modulo ``24*3600``.
    If ``inverse``, then do the inverse operation.
    In this case, if ``mod24`` also, then first take the number of
    seconds modulo ``24*3600``.
    """
    if not inverse:
        try:
            hours, mins, seconds = x.split(":")
            result = int(hours) * 3600 + int(mins) * 60 + int(seconds)
            if mod24:
                result %= 24 * 3600
        except:
            result = np.nan
    else:
        try:
            seconds = int(x)
            if mod24:
                seconds %= 24 * 3600
            hours, remainder = divmod(seconds, 3600)
            mins, secs = divmod(remainder, 60)
            result = f"{hours:02d}:{mins:02d}:{secs:02d}"
        except:
            result = np.nan
    return result


def timestr_mod24(timestr: str) -> int:
    """
    Given a GTFS HH:MM:SS time string, return a timestring in the same
    format but with the hours taken modulo 24.
    """
    try:
        hours, mins, secs = [int(x) for x in timestr.split(":")]
        hours %= 24
        result = f"{hours:02d}:{mins:02d}:{secs:02d}"
    except:
        result = None
    return result


def weekday_to_str(
    weekday: Union[int, str], *, inverse: bool = False
) -> Union[int, str]:
    """
    Given a weekday number (integer in the range 0, 1, ..., 6),
    return its corresponding weekday name as a lowercase string.
    Here 0 -> 'monday', 1 -> 'tuesday', and so on.
    If ``inverse``, then perform the inverse operation.
    """
    s = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    if not inverse:
        try:
            return s[weekday]
        except:
            return
    else:
        try:
            return s.index(weekday)
        except:
            return


def get_segment_length(
    linestring: LineString, p: Point, q: Optional[Point] = None
) -> float:
    """
    Given a Shapely linestring and two Shapely points,
    project the points onto the linestring, and return the distance
    along the linestring between the two points.
    If ``q is None``, then return the distance from the start of the
    linestring to the projection of ``p``.
    The distance is measured in the native coordinates of the linestring.
    """
    # Get projected distances
    d_p = linestring.project(p)
    if q is not None:
        d_q = linestring.project(q)
        d = abs(d_p - d_q)
    else:
        d = d_p
    return d


def get_max_runs(x) -> np.array:
    """
    Given a list of numbers, return a NumPy array of pairs
    (start index, end index + 1) of the runs of max value.

    Example::

        >>> get_max_runs([7, 1, 2, 7, 7, 1, 2])
        array([[0, 1],
               [3, 5]])

    Assume x is not empty.
    Recipe comes from
    `Stack Overflow <http://stackoverflow.com/questions/1066758/find-length-of-sequences-of-identical-values-in-a-numpy-array>`_.
    """
    # Get 0-1 array where 1 marks the max values of x
    x = np.array(x)
    m = np.max(x)
    y = (x == m) * 1
    # Bound y by zeros to detect runs properly
    bounded = np.hstack(([0], y, [0]))
    # Get 1 at run starts and -1 at run ends
    diffs = np.diff(bounded)
    run_starts = np.where(diffs > 0)[0]
    run_ends = np.where(diffs < 0)[0]
    return np.array([run_starts, run_ends]).T
    # # Get lengths of runs and find index of longest
    # idx = np.argmax(run_ends - run_starts)
    # return run_starts[idx], run_ends[idx]


def get_peak_indices(times: List, counts: List) -> np.array:
    """
    Given an increasing list of times as seconds past midnight and a
    list of trip counts at those respective times,
    return a pair of indices i, j such that times[i] to times[j] is
    the first longest time period such that for all i <= x < j,
    counts[x] is the max of counts.
    Assume times and counts have the same nonzero length.
    """
    max_runs = get_max_runs(counts)

    def get_duration(a):
        return times[a[1]] - times[a[0]]

    index = np.argmax(np.apply_along_axis(get_duration, 1, max_runs))
    return max_runs[index]


def get_convert_dist(
    dist_units_in: str, dist_units_out: str
) -> Callable[[float], float]:
    """
    Return a function of the form

      distance in the units ``dist_units_in`` ->
      distance in the units ``dist_units_out``

    Only supports distance units in :const:`constants.DIST_UNITS`.
    """
    di, do = dist_units_in, dist_units_out
    DU = cs.DIST_UNITS
    if not (di in DU and do in DU):
        raise ValueError(f"Distance units must lie in {DU}")

    d = {
        "ft": {"ft": 1, "m": 0.3048, "mi": 1 / 5280, "km": 0.000_304_8},
        "m": {"ft": 1 / 0.3048, "m": 1, "mi": 1 / 1609.344, "km": 1 / 1000},
        "mi": {"ft": 5280, "m": 1609.344, "mi": 1, "km": 1.609_344},
        "km": {"ft": 1 / 0.000_304_8, "m": 1000, "mi": 1 / 1.609_344, "km": 1},
    }
    return lambda x: d[di][do] * x


def almost_equal(f: DataFrame, g: DataFrame) -> bool:
    """
    Return ``True`` if and only if the given DataFrames are equal after
    sorting their columns names, sorting their values, and
    reseting their indices.
    """
    if f.empty or g.empty:
        return f.equals(g)
    else:
        # Put in canonical order
        F = (
            f.sort_index(axis=1)
            .sort_values(list(f.columns))
            .reset_index(drop=True)
        )
        G = (
            g.sort_index(axis=1)
            .sort_values(list(g.columns))
            .reset_index(drop=True)
        )
        return F.equals(G)


def is_not_null(df: DataFrame, col_name: str) -> bool:
    """
    Return ``True`` if the given DataFrame has a column of the given
    name (string), and there exists at least one non-NaN value in that
    column; return ``False`` otherwise.
    """
    if (
        isinstance(df, pd.DataFrame)
        and col_name in df.columns
        and df[col_name].notnull().any()
    ):
        return True
    else:
        return False


def get_utm_crs(lat: float, lon: float) -> Dict:
    """
    Return a GeoPandas coordinate reference system (CRS) dictionary
    corresponding to the UTM projection appropriate to the given WGS84
    latitude and longitude.
    """
    zone = utm.from_latlon(lat, lon)[2]
    south = lat < 0
    return {
        "proj": "utm",
        "zone": zone,
        "south": south,
        "ellps": "WGS84",
        "datum": "WGS84",
        "units": "m",
        "no_defs": True,
    }


def linestring_to_utm(linestring: LineString) -> LineString:
    """
    Given a Shapely LineString in WGS84 coordinates,
    convert it to the appropriate UTM coordinates.
    If ``inverse``, then do the inverse.
    """
    proj = lambda x, y: utm.from_latlon(y, x)[:2]
    return transform(proj, linestring)


def get_active_trips_df(trip_times: DataFrame) -> DataFrame:
    """
    Count the number of trips in ``trip_times`` that are active
    at any given time.

    Parameters
    ----------
    trip_times : DataFrame
        Contains columns

        - start_time: start time of the trip in seconds past midnight
        - end_time: end time of the trip in seconds past midnight

    Returns
    -------
    Series
        index is times from midnight when trips start and end,
        values are number of active trips for that time

    """
    active_trips = (
        pd.concat(
            [
                pd.Series(1, trip_times.start_time),  # departed add 1
                pd.Series(-1, trip_times.end_time),  # arrived subtract 1
            ]
        )
        .groupby(level=0, sort=True)
        .sum()
        .cumsum()
        .ffill()
    )
    return active_trips


def combine_time_series(
    time_series_dict: Dict, kind: str, *, split_directions: bool = False
) -> DataFrame:
    """
    Combine the many time series DataFrames in the given dictionary
    into one time series DataFrame with hierarchical columns.

    Parameters
    ----------
    time_series_dict : dictionary
        Has the form string -> time series
    kind : string
        ``'route'`` or ``'stop'``
    split_directions : boolean
        If ``True``, then assume the original time series contains data
        separated by trip direction; otherwise, assume not.
        The separation is indicated by a suffix ``'-0'`` (direction 0)
        or ``'-1'`` (direction 1) in the route ID or stop ID column
        values.

    Returns
    -------
    DataFrame
        Columns are hierarchical (multi-index).
        The top level columns are the keys of the dictionary and
        the second level columns are ``'route_id'`` and
        ``'direction_id'``, if ``kind == 'route'``, or 'stop_id' and
        ``'direction_id'``, if ``kind == 'stop'``.
        If ``split_directions``, then third column is
        ``'direction_id'``; otherwise, there is no ``'direction_id'``
        column.

    """
    if kind not in ["stop", "route"]:
        raise ValueError("kind must be 'stop' or 'route'")

    names = ["indicator"]
    if kind == "stop":
        names.append("stop_id")
    else:
        names.append("route_id")

    if split_directions:
        names.append("direction_id")

    def process_index(k):
        a, b = k.rsplit("-", 1)
        return a, int(b)

    frames = list(time_series_dict.values())
    new_frames = []
    if split_directions:
        for f in frames:
            ft = f.T
            ft.index = pd.MultiIndex.from_tuples(
                [process_index(k) for (k, __) in ft.iterrows()]
            )
            new_frames.append(ft.T)
    else:
        new_frames = frames
    result = pd.concat(
        new_frames, axis=1, keys=list(time_series_dict.keys()), names=names
    )

    return result.rename_axis("datetime", axis="index")


def downsample(time_series: DataFrame, freq: str) -> DataFrame:
    """
    Downsample the given route, stop, or feed time series,
    (outputs of :func:`.routes.compute_route_time_series`,
    :func:`.stops.compute_stop_time_series`, or
    :func:`.miscellany.compute_feed_time_series`,
    respectively) to the given Pandas frequency string (e.g. '15Min').
    Return the given time series unchanged if the given frequency is
    shorter than the original frequency.
    """

    f = time_series.copy()

    # Can't downsample to a shorter frequency
    if f.empty or pd.tseries.frequencies.to_offset(
        freq
    ) <= pd.tseries.frequencies.to_offset(pd.infer_freq(f.index)):
        return f

    result = None
    if "stop_id" in time_series.columns.names:
        # It's a stops time series
        result = f.resample(freq).sum(min_count=1)
    else:
        # It's a route or feed time series.
        inds = [
            "num_trips",
            "num_trip_starts",
            "num_trip_ends",
            "service_distance",
            "service_duration",
        ]
        frames = []

        # Resample num_trips in a custom way that depends on
        # num_trips and num_trip_ends
        def agg_num_trips(group):
            return group["num_trips"].iloc[-1] + group["num_trip_ends"].iloc[
                :-1
            ].sum(min_count=1)

        num_trips = f.groupby(pd.Grouper(freq=freq)).apply(agg_num_trips)
        frames.append(num_trips)

        # Resample the rest of the indicators via summing, preserving all-NaNs
        frames.extend(
            [
                f[ind].resample(freq).agg(lambda x: x.sum(min_count=1))
                for ind in inds[1:]
            ]
        )

        g = pd.concat(frames, axis=1, keys=inds)

        # Calculate speed and add it to f. Can't resample it.
        speed = (g.service_distance / g.service_duration).fillna(
            g.service_distance
        )
        speed = pd.concat({"service_speed": speed}, axis=1)
        result = pd.concat([g, speed], axis=1)

    # Reset column names and sort the hierarchical columns to allow slicing;
    # see http://pandas.pydata.org/pandas-docs/stable/advanced.html#sorting-a-multiindex
    result.columns.names = f.columns.names
    result = result.sort_index(axis=1, sort_remaining=True)

    # Set frequency, which is not automatically set
    result.index.freq = freq

    return result


def unstack_time_series(time_series: DataFrame) -> DataFrame:
    """
    Given a route, stop, or feed time series of the form output by the functions,
    :func:`compute_stop_time_series`, :func:`compute_route_time_series`, or
    :func:`compute_feed_time_series`, respectively, unstack it to return a DataFrame
    of with the columns:

    - ``"datetime"``
    - the columns ``time_series.columns.names``
    - ``"value"``: value at the datetime and other columns

    """
    col_names = time_series.columns.names
    return (
        time_series.unstack()
        .pipe(pd.DataFrame)
        .reset_index()
        .rename(columns={0: "value", "level_2": "datetime"})
        # Reorder columns
        .filter(["datetime"] + col_names + ["value"])
        .sort_values(["datetime"] + col_names)
    )


def restack_time_series(unstacked_time_series: DataFrame) -> DataFrame:
    """
    Given an unstacked stop, route, or feed time series in the form
    output by the function :func:`unstack_time_series`, restack it into
    its original time series form.
    """
    f = unstacked_time_series
    columns = [c for c in f.columns if c not in ["datetime", "value"]]
    g = f.pivot_table(index="datetime", columns=columns).value.sort_index(
        axis="columns"
    )

    # Get time series frequency
    if g.index.size > 1:
        hours = (g.index[1] - g.index[0]).components.hours
        if hours != 0:
            freq = f"{hours}H"
        else:
            freq = "D"
    else:
        freq = "D"

    # If necessary, insert missing dates and NaNs to complete series index
    num_dates = len(set(g.index.date))
    if num_dates > 1:
        end_datetime = pd.to_datetime(
            f"{g.index.date[-1]:%Y-%m-%d}" + " 23:59:59"
        )
        new_index = pd.date_range(
            g.index[0], end_datetime, freq=freq, name="datetime"
        )
        g = g.reindex(new_index)

    g.index.freq = freq

    return g


def make_html(d: Dict) -> str:
    """
    Convert the given dictionary into an HTML table (string) with
    two columns: keys of dictionary, values of dictionary.
    """
    return j2t.convert(
        d, table_attributes={"class": "table table-condensed table-hover"}
    )
