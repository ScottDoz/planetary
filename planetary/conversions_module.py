# -*- coding: utf-8 -*-
"""
Created on Fri Oct 11 18:27:29 2019

@author: Scott Dorrington

Conversions Module

"""

import numpy as np
import spiceypy
from osgeo import osr


def geodetic_to_ecef(r,long,lat):
    '''
    Convert geodetic (lat,long,r) coordinates to rectangular coordinates (x,y,z)
    in a body-fixed reference frame (equivalent to ECEF).
    This implementation uses spiceypy routine spiceypy.spiceypy.latrec
    
    Inputs:
    r : float
        radius (m)
    long : float
        longitude (rad)
    lat : float
        latitude (rad)
    
    Outputs:
    x, y, z = position in ecef coords
    
    ### Note ###
    The python implementation of the latrec_c function is not vectorized.
    This function uses a loop to handle transformation of multiple coordinates.
    This could be slow for large data sets, look into vectorizing this later
    using the numpy np.vectorize function.
    '''
    
    # Initialize vectors
    x = np.zeros(r.shape)
    y = np.zeros(r.shape)
    z = np.zeros(r.shape)
    # Loop through elements
    for i in range(len(r)):
        xi,yi,zi = spiceypy.spiceypy.latrec(r[i],long[i],lat[i])
        x[i] = xi
        y[i] = yi
        z[i] = zi
        # Or use spiceypy.spiceypy.georec(lon, lat, alt, re, f)
    
    return x, y, z

def ecef_to_geodetic(xyz):
    '''
    Convert rectangular coordinates (x,y,z) to geodetic (lat,long,r) coordinates
    in a body-fixed reference frame (equivalent to ECEF).
    This implementation uses spiceypy routine spiceypy.spiceypy.reclat
    
    Inputs:
    xyz = position in ecef coords (numpy array)
    
    Outputs:
    r : float
        radius (m)
    long : float
        longitude (rad)
    lat : float
        latitude (rad)
    
    
    ### Note ###
    The python implementation of the reclat_c function is not vectorized.
    This function uses a loop to handle transformation of multiple coordinates.
    This could be slow for large data sets, look into vectorizing this later
    using the numpy np.vectorize function.
    '''
    
    # Initialize vectors
    r = np.zeros(len(xyz))
    long = np.zeros(len(xyz))
    lat = np.zeros(len(xyz))
    # Loop through elements
    for i in range(len(xyz)):
        ri,longi,lati = spiceypy.spiceypy.reclat(xyz[i])
        r[i] = ri # Radius
        long[i] = longi
        lat[i] = lati
        # Or use spiceypy.spiceypy.georec(lon, lat, alt, re, f)
    
    return r, long, lat


def rec_to_rat(r,lat,long):
    '''
    Convert geodetic (lat,long,r) coordinates to rectangular coordinates (x,y,z)
    in a body-fixed reference frame (equivalent to ECEF).
    This implementation uses spiceypy routine spiceypy.spiceypy.latrec
    
    Inputs:
    r : float
        radius (m)
    long : float
        longitude (rad)
    lat : float
        latitude (rad)
    
    Outputs:
    x, y, z = position in ecef coords
    
    ### Note ###
    The python implementation of the latrec_c function is not vectorized.
    This function uses a loop to handle transformation of multiple coordinates.
    This could be slow for large data sets, look into vectorizing this later
    using the numpy np.vectorize function.
    '''
    
    # Initialize vectors
    x = np.zeros(r.shape)
    y = np.zeros(r.shape)
    z = np.zeros(r.shape)
    # Loop through elements
    for i in range(len(r)):
        xi,yi,zi = spiceypy.spiceypy.latrec(r[i],long[i],lat[i])
        x[i] = xi
        y[i] = yi
        z[i] = zi
        # Or use spiceypy.spiceypy.georec(lon, lat, alt, re, f)
    
    return x, y, z


def ecef_to_enu(x,y,z,lat0,long0,r0=0):
    '''
    Convert rectangular coordinates (ECEF) to local East-North-Up ENU coordinates 
    
    This implementation uses a simple 3x3 transformation matrix that performs 
    two rotations to re-orient the coordinate frame. The reverse transformation
    can be obtained by the inverse of the rotation matrix.
    
    See: https://gssc.esa.int/navipedia/index.php/Transformations_between_ECEF_and_ENU_coordinates
    where (λ,φ)  are taken as the spherical longitude and latitude 
    
    Input:
    x : 1xN numpy
        array of x-coordinates
    y : 1xN numpy
        array of y-coordinates
    z : 1xN numpy
        array of z-coordinates
    lat0 : float
        latitude of origin (rad)
    long0 : float
        longitude of origin (rad)
    r0 : float
        radius of origin above (m)    
    '''
    
    R =  np.array([[-np.sin(long0), np.cos(long0), 0],
                    [-np.cos(long0)*np.sin(lat0), -np.sin(long0)*np.sin(lat0), np.cos(lat0)],
                    [np.cos(long0)*np.cos(lat0), np.sin(long0)*np.cos(lat0), np.sin(lat0) ]])
    
    
    
    ecef = np.block([[x],[y],[z] ]) # 3xN vector or x,y,z coordinates
    
    
    enu = np.matmul(R, ecef)
    
    # Extract values
    e = enu[0,...]
    n = enu[1,...]
    u = enu[2,...] 
    
    # Offset up by reference radius
    u -= r0
    
    
    return e,n,u


def convertXY(xy_source, inproj, outproj):
    '''
    This function converts coordinates between different map projections
    See: https://stackoverflow.com/questions/20488765/plot-gdal-raster-using-matplotlib-basemap
    '''

    shape = xy_source[0,:,:].shape
    size = xy_source[0,:,:].size

    # the ct object takes and returns pairs of x,y, not 2d grids
    # so the the grid needs to be reshaped (flattened) and back.
    ct = osr.CoordinateTransformation(inproj, outproj)
    xy_target = np.array(ct.TransformPoints(xy_source.reshape(2, size).T))

    xx = xy_target[:,0].reshape(shape)
    yy = xy_target[:,1].reshape(shape)

    return xx, yy



#%% Polar Stereographic Conversions

# The following functions polar_xy_to_lonlat and polar_lonlat_to_xy have been 
# adapted from the 

def polar_xy_to_lonlat(x, y, true_scale_lat, re, e, hemisphere):
    """
    Convert from Polar Stereographic (x, y) coordinates to
    geodetic longitude and latitude.
    
    
    Args:
        x (float): X coordinate(s) in km
        y (float): Y coordinate(s) in km
        true_scale_lat (float): true-scale latitude in degrees (aka standard parallel)
        hemisphere (1 or -1): 1 for Northern hemisphere, -1 for Southern
        re (float): Earth radius in km
        e (float): Earth eccentricity
    Returns:
        If x and y are scalars then the result is a
        two-element list containing [longitude, latitude].
        If x and y are numpy arrays then the result will be a two-element
        list where the first element is a numpy array containing
        the longitudes and the second element is a numpy array containing
        the latitudes.
        
    Adapted from https://github.com/nsidc/polar_stereo/blob/master/source/polar_convert.py
    
    Copyright (c) 2019 Regents of the University of Colorado

    This software was developed by the National Snow and Ice Data Center with 
    funding from multiple sources.

    Permission is hereby granted, free of charge, to any person obtaining a copy 
    of this software and associated documentation files (the "Software"), to 
    deal in the Software without restriction, including without limitation the 
    rights to use, copy, modify, merge, publish, distribute, sublicense, and/or 
    sell copies of the Software, and to permit persons to whom the Software is 
    furnished to do so, subject to the following conditions:
    
    The above copyright notice and this permission notice shall be included in 
    all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, 
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN 
    THE SOFTWARE.
    
    """

    e2 = e * e
    slat = true_scale_lat * np.pi / 180
    rho = np.sqrt(x ** 2 + y ** 2)

    if abs(true_scale_lat - 90.) < 1e-5:
        t = rho * np.sqrt((1 + e) ** (1 + e) * (1 - e) ** (1 - e)) / (2 * re)
    else:
        cm = np.cos(slat) / np.sqrt(1 - e2 * (np.sin(slat) ** 2))
        t = np.tan((np.pi / 4) - (slat / 2)) / \
            ((1 - e * np.sin(slat)) / (1 + e * np.sin(slat))) ** (e / 2)
        t = rho * t / (re * cm)

    chi = (np.pi / 2) - 2 * np.arctan(t)
    lat = chi + \
        ((e2 / 2) + (5 * e2 ** 2 / 24) + (e2 ** 3 / 12)) * np.sin(2 * chi) + \
        ((7 * e2 ** 2 / 48) + (29 * e2 ** 3 / 240)) * np.sin(4 * chi) + \
        (7 * e2 ** 3 / 120) * np.sin(6 * chi)
    lat = hemisphere * lat * 180 / np.pi
    lon = np.arctan2(hemisphere * x, -hemisphere * y)
    lon = hemisphere * lon * 180 / np.pi
    lon = lon + np.less(lon, 0) * 360
    return lon, lat


def polar_lonlat_to_xy(longitude, latitude, true_scale_lat, re, e, hemisphere):
    """
    Convert from geodetic longitude and latitude to Polar Stereographic
    (X, Y) coordinates in km.
    
    Adapted from https://github.com/nsidc/polar_stereo/blob/master/source/polar_convert.py
    
    
    Args:
        longitude (float): longitude or longitude array in degrees
        latitude (float): latitude or latitude array in degrees (positive)
        true_scale_lat (float): true-scale latitude in degrees (aka standard parallel)
        re (float): Earth radius in km
        e (float): Earth eccentricity
        hemisphere (1 or -1): Northern or Southern hemisphere
    Returns:
        If longitude and latitude are scalars then the result is a
        two-element list containing [X, Y] in km.
        If longitude and latitude are numpy arrays then the result will be a
        two-element list where the first element is a numpy array containing
        the X coordinates and the second element is a numpy array containing
        the Y coordinates.
    
    Adapted from https://github.com/nsidc/polar_stereo/blob/master/source/polar_convert.py
    
    Copyright (c) 2019 Regents of the University of Colorado

    This software was developed by the National Snow and Ice Data Center with 
    funding from multiple sources.

    Permission is hereby granted, free of charge, to any person obtaining a copy 
    of this software and associated documentation files (the "Software"), to 
    deal in the Software without restriction, including without limitation the 
    rights to use, copy, modify, merge, publish, distribute, sublicense, and/or 
    sell copies of the Software, and to permit persons to whom the Software is 
    furnished to do so, subject to the following conditions:
    
    The above copyright notice and this permission notice shall be included in 
    all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, 
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN 
    THE SOFTWARE.
    
    """

    lat = abs(latitude) * np.pi / 180
    lon = longitude * np.pi / 180
    slat = true_scale_lat * np.pi / 180

    e2 = e * e

    # Snyder (1987) p. 161 Eqn 15-9
    t = np.tan(np.pi / 4 - lat / 2) / \
        ((1 - e * np.sin(lat)) / (1 + e * np.sin(lat))) ** (e / 2)

    if abs(90 - true_scale_lat) < 1e-5:
        # Snyder (1987) p. 161 Eqn 21-33
        rho = 2 * re * t / np.sqrt((1 + e) ** (1 + e) * (1 - e) ** (1 - e))
    else:
        # Snyder (1987) p. 161 Eqn 21-34
        tc = np.tan(np.pi / 4 - slat / 2) / \
            ((1 - e * np.sin(slat)) / (1 + e * np.sin(slat))) ** (e / 2)
        mc = np.cos(slat) / np.sqrt(1 - e2 * (np.sin(slat) ** 2))
        rho = re * mc * t / tc

    x = rho * hemisphere * np.sin(hemisphere * lon)
    y = -rho * hemisphere * np.cos(hemisphere * lon)
    return [x, y]

