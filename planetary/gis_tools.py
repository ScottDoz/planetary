# -*- coding: utf-8 -*-
"""
Created on Mon Sep 28 14:57:34 2020

@author: scott

GIS Tools module
----------------

Contains functions for manipulating GIS data. 

"""

# Standard imports
import numpy as np
import pandas as pd
from pprint import pprint
import os
import sys
import subprocess
from pathlib import Path

import pdb

# GIS packages
from owslib.wms import WebMapService
from osgeo import gdal, osr, ogr
import cartopy.crs as ccrs
import pyproj
import geopandas as gpd
from shapely.geometry import Polygon

# 3D mesh packages
import pyvista as pv
# import vtkplotter
import vedo

# Package imports
from planetary.conversions_module import geodetic_to_ecef, polar_xy_to_lonlat, ecef_to_enu

#%% Raster Reading/Writing ----------------------------------------------------

# GIS methods
def tif_from_wms(wms,layers,s_srs,bbox,size=(600,600),format='image/tiff', # Required arguments
                 t_srs=None, # Target srs projection (srs string)
                 styles=None, transparent=True,bgcolor=None,method=None, # Optional arguments
                 filename='Unnamed_Raster.tif',data_dir=None,
                 planet=None, **kwargs):
    '''
    Generate a raster image from a wms response.
        
    Workflow:
    1. Get wms response
    2. Save the image to a file
    3. Reproject image + save
    4. Read in image data

    Parameters
    ----------
    wms : TYPE
        DESCRIPTION.
    layers : TYPE
        DESCRIPTION.
    s_srs : TYPE
        DESCRIPTION.
    bbox : TYPE
        DESCRIPTION.
    size : TYPE, optional
        DESCRIPTION. The default is (600,600).
    format : TYPE, optional
        DESCRIPTION. The default is 'image/tiff'.
    # Required arguments                 
    t_srs : TYPE, optional
        DESCRIPTION. The default is None.
        
    # Target srs projection (srs string)                 
    styles : TYPE, optional
        DESCRIPTION. The default is None.
    transparent : TYPE, optional
        DESCRIPTION. The default is True.
    bgcolor : TYPE, optional
        DESCRIPTION. The default is None.
    method : TYPE, optional
        DESCRIPTION. The default is None.
    # Optional arguments                 
    filename : TYPE, optional
        DESCRIPTION. The default is 'Unnamed_Raster'.
    data_dir : TYPE, optional
        DESCRIPTION. The default is None.
    planet : TYPE, optional
        DESCRIPTION. The default is None.
    kwargs : dict, optional
        Dictionary of additional key word arguments.
        polar_raster_shape

    Returns
    -------
    None.

    '''
    # Generate a raster tif from a wms
    print('\nGenerating {} from WMS'.format(filename))
    
    # Adjust size/bbox for square polar stereographic plot --------------------
    # Need to calculate the size of the bounding box to request from the wms,
    # and the size of the bounding box to clip to get the final raster.
    
    # Look for keyword argument
    square_polar_flag = False # Set Default
    if 'polar_raster_shape' in kwargs.keys():
        
        # Define proj4 string of target
        if t_srs == 'IAU2000:30120':
            # Moon south pole stereographic
            t_proj4 = '+proj=stere +lat_0=-90 +lon_0=0 +k=1 +x_0=0 +y_0=0 +a=1737400 +b=1737400 +units=m +no_defs '
            
            # Proj4 string of source
            if s_srs == 'EPSG:4326':
                # Use equivalent projection for moon IAU2000:30100
                s_proj4 = '+proj=longlat +a=1737400 +b=1737400 +no_defs '
            
        else:
            t_proj4 = None
            s_proj4 = None
        # TODO: Add other projections
        
        if (t_proj4 is not None) & (kwargs['polar_raster_shape']=='square'):
            
            # Request square polar stereographic map
            square_polar_flag = True # Commit to rescaling and clipping raster.
            
            # 1. Project the bounding box to the target srs
            
            # Extract components of region's bbox in lat/long coords
            left = bbox[0]
            bottom = bbox[1]
            right = bbox[2]
            top = bbox[3]
            
            # Create a geopandas shape of the bounding box
            # (clockwise from bottom left corner)
            # (left,bottom),(left,top),(right,top),(right,bottom)
            lon_point_list = [left,left,right,right]
            lat_point_list = [bottom,top,top,bottom]            
            df = pd.DataFrame({'Longitude': lon_point_list, 'Latitude': lat_point_list})
            gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.Longitude, df.Latitude))
            gdf.crs = s_proj4 # Set projection of gdf
            # Project to output srs            
            gdf['geometry_t_srs'] = gdf['geometry'].to_crs(crs = t_proj4)
            # Add columns for x and y coords
            gdf['X_t_srs'] = gdf['geometry_t_srs'].apply(lambda x: x.x )
            gdf['Y_t_srs'] = gdf['geometry_t_srs'].apply(lambda x: x.y )
            
            # Compute radius of each point from x,y coordinates
            gdf['radius_t_srs'] = gdf['geometry_t_srs'].apply(lambda x: np.sqrt(x.x**2 + x.y**2) )
            # Get maximum radius
            r0 = max(gdf['radius_t_srs'])
            # Construct bbox of final target raster
            # (extent that the final raster will be clipped to)
            bbox_target = (-r0,-r0,r0,r0,t_srs)
            size_target = size
            
            # 2. Increase extent of bbox for wms request to include corner regions
            # Half-width of the raster computed from the radius of the raster
            # Increase by factor of sqrt(2) (hypotenuse of right triange)
            r1 = r0*np.sqrt(2)
            
            # Create a new dataframe with scaled points
            scale_factor = np.sqrt(2)
            dfscaled = pd.DataFrame({'X': gdf.X_t_srs*scale_factor, 'Y': gdf.Y_t_srs*scale_factor})
            gdfscaled = gpd.GeoDataFrame(dfscaled, geometry=gpd.points_from_xy(dfscaled.X, dfscaled.Y))
            gdfscaled.crs = t_proj4 # Set projection
            
            # 3. Project back to source srs
            gdfscaled['geometry_s_srs'] = gdfscaled['geometry'].to_crs(crs = s_proj4)
            # Add columns for lat and long coords
            gdfscaled['Longitude'] = gdfscaled['geometry_s_srs'].apply(lambda x: x.x )
            gdfscaled['Latitude'] = gdfscaled['geometry_s_srs'].apply(lambda x: x.y )
            
            # 4. Construct the bbox and size to use in wms request
            max_lat = max(gdfscaled.Latitude)
            min_lat = min(gdfscaled.Latitude)
            bbox = (-180,min_lat,180,max_lat,s_srs) # Left,bottom,right,top
            size = (int(np.ceil(size[0]*scale_factor)), int(np.ceil(size[1]*scale_factor)))
            
    
    # 1. Get wms response
    response = wms.getmap(layers=layers, bbox=bbox, 
                          srs=s_srs, size=size, format='image/tiff')
    # Get metadata on layer contents
    layer_contents = wms.contents[layers[0]]
    title = layer_contents.title
    abstract = layer_contents.abstract
    
    
    # 2. Save response as a tif file
    fullfilename = data_dir/filename # Absolute path to file
    with open(fullfilename,'wb') as file:
        file.write(response.read())
    file.close() # Close the file
    print('{} raster saved to disk.'.format(filename))
    # Add a description with metadata
    # FIXME: This doesn't seem to be working
    ds = gdal.Open(str(fullfilename),gdal.GA_Update) # Open file alowing updates
    desc = title + '. ' + abstract # Construct description string
    ds.SetDescription(desc) # Set the desciption
    ds = None # Close the file
    
    
    # 3a. Convert datum
    # if (s_srs in ['EPSG:4326']) & (planet not in ['Earth','earth']):
    if s_srs in ['EPSG:4326']:
        # Using Earth-based equatorial projection with a different planet.
        # Need to change the datum/geoid of the tif tile to match the planet.
        convert_datum_to_IAU(fullfilename, planet)
    
    # 3b. Reproject to t_srs
    if t_srs != s_srs:
        reproject_image(fullfilename,t_srs)
    
    # 4. (Resample and clip polar rasters)
    if square_polar_flag == True:
        # Clip raster to target bbox and size

        # Get inputs for -projWin <ulx> <uly> <lrx> <lry>
        # (different ordering to bbox)
        projwin = [bbox_target[0],bbox_target[3], bbox_target[2],bbox_target[1]]
        # Perform resampling
        resample_image(fullfilename,fullfilename,projwin=projwin,size=size_target)
        
        
        # # Perform resampling with python GDAL bindings
        # ds = gdal.Open(str(fullfilename),gdal.GA_Update) # allow update
        # ds = gdal.Translate(str(fullfilename), ds, projWin = projwin, 
        #                     width=size_target[0], height=size_target[1])
        # ds = None # Close file
        
    
    
    return

def convert_datum_to_IAU(fullfilename, planet):
    '''
    Convert a tif file in EPSG:4326 srs to the equivalent IAU srs.
    Moon: EPSG:4326 == IAU2000:301200
    
    *** Warning. This method works for Lunaserv with source EPSG:4326.
    Should be careful with other wms that may have different source srs.
    '''
    
    # Open the image using gdal (allowing update)
    src_ds = gdal.Open(str(fullfilename),gdal.GA_Update) # Source dataset
    
    # Get Input SRS -------------------------------------------------------
    
    # Projection in WKT
    inproj_wkt = src_ds.GetProjection()
    # e.g. 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST],AUTHORITY["EPSG","4326"]]'
    # Note: WGS84 = EPSG4326 = PlateCarree
    # FIXME: No projection info when using reprojection with python bindings.
    
    # Convert projection to osr SpatialReference object
    inproj = osr.SpatialReference()
    inproj.ImportFromWkt(inproj_wkt)
    
    # Proj4 string
    inproj_proj4 = inproj.ExportToProj4() 
    
    # Geotransform
    inproj_gt = src_ds.GetGeoTransform()
    
    # Specify new srs ----------------------------------------------------
    
    # Set the WKT string of the projection (https://spatialreference.org)
    if planet in ['Luna','Moon','luna','moon']:
        # Swap EPSG:4326 with IAU2000:30100
        outproj_proj4 = '+proj=longlat +a=1737400 +b=1737400 +no_defs '
        # WKT
        outwkt = 'GEOGCS["Moon 2000",DATUM["D_Moon_2000",SPHEROID["Moon_2000_IAU_IAG",1737400.0,0.0]],PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]'
    elif planet in ['Mars','mars']:
        # Swap EPSG:4326 with IAU2000:49900
        outproj_proj4 = '+proj=longlat +a=3396190 +b=3376200 +no_defs '
        # WKT
        outwkt = 'GEOGCS["Mars 2000",DATUM["D_Mars_2000",SPHEROID["Mars_2000_IAU_IAG",3396190.0,169.89444722361179]],PRIMEM["Greenwich",0],UNIT["Decimal_Degree",0.0174532925199433]]'
    
    elif planet in ['Earth','earth']:
        # Swap EPSG:4326 with IAU2000:39900
        outproj_proj4 = '+proj=longlat +a=6378140 +b=6356750 +no_defs '
        # WKT
        outwkt = 'GEOGCS["Earth 2000",DATUM["D_Earth_2000",SPHEROID["Earth_2000_IAU_IAG",6378140.0,298.18326320710611]],PRIMEM["Greenwich",0],UNIT["Decimal_Degree",0.0174532925199433]]'
    
    # TODO: Set equivalent projections for other planets
    
    
    # # Create srs object
    # outproj = osr.SpatialReference()
    # outproj.ImportFromProj4(outproj_proj4)
    # outproj_wkt = outproj.ExportToWkt() # Well Known Text
    

    
    # Reset properties of the datasource ----------------------------------
    # src_ds.SetProjection(outproj_wkt) # New projection
    # src_ds.SetGeoTransform(inproj_gt) # Unchanged
    
    src_ds.SetProjection(outwkt)
    print('Reset geoid')
    
    # Close file
    src_ds = None # Save and close
    
    return

def scale_dem_raster(fullfilename,scale):
    '''
    Scale elevation values of DEM raster.
    E.g. convert dem from km to m.

    Parameters
    ----------
    fullfilename : TYPE
        DESCRIPTION.
    scale : TYPE
        DESCRIPTION.

    Returns
    -------
    None
    '''
    
    
    # Extract data from raster file
    from planetary.mesh_utils import xyz_from_dem
    X, Y, data, inproj_proj4, proj_wkt = xyz_from_dem(fullfilename)
    elev = data.copy() # Elevation data [km]
    elev_min = elev.min()
    elev_max = elev.max()
    
    outfile = fullfilename.parent/'temp_scaled_dem.tif'
    
    cmd = f"gdal_translate -scale {elev_min} {elev_max} {elev_min*scale} {elev_max*scale} {fullfilename} {outfile}"
    
    print('Scaling DEM elevation with gdal_translate\n')
    print(cmd)
    print('')
    
    # Execute the command in console
    p = subprocess.Popen(cmd, shell=True, cwd=str(fullfilename.parent) ,stderr=subprocess.PIPE)
    # Wait until process is finished
    (output, err) = p.communicate()
    p_status = p.wait() # This makes the wait possible
    print(err) # Print any error to screen
    
    # Update file
    if outfile.exists():
        fullfilename.unlink() # Delete old file
        outfile.rename(fullfilename)
        print("Renamed temp file")
    
    return


def reproject_image(fullfilename,t_srs):
    '''
    Reproject a raster image using gdalwarp command line function.

    Parameters
    ----------
    fullfilename : Pathlib
        Full filename of input raster.
    t_srs : TYPE
        Target spatial reference system.

    Returns
    -------
    None.

    '''
    
    # Change the name of the input file
    out_file = fullfilename # Output filename (original name)
    in_file = Path(fullfilename.parent, 'infile_' + fullfilename.stem + fullfilename.suffix)
    # Change name of original file to in_file name
    fullfilename.rename(in_file)
    
    # Get data directory
    data_dir = fullfilename.parent
    
    
    # Open the image using gdal
    src_ds = gdal.Open(str(in_file)) # Source dataset
    src_nodataval = src_ds.GetRasterBand(1).GetNoDataValue() 
    
    # Set destination nodata
    if src_nodataval is None:
        dst_nodataval = -9999
    else:
        dst_nodataval = src_nodataval
    
    
    
    # Get proj4 string of target srs
    if t_srs in ['IAU2000:30120','South Pole','South']:
        # Lunar South pole stereographic
        # https://spatialreference.org/ref/iau2000/30120/
        
        # IAU2000:30120 
        t_srs = r'"+proj=stere +lat_0=-90 +lon_0=0 +k=1 +x_0=0 +y_0=0 +a=1737400 +b=1737400 +units=m +no_defs "'
        # (This method fails)
        
        # Make a copy of the string
        proj4str = t_srs
        
        # Cartopy CRS
        ellipsoid = ccrs.Globe(semimajor_axis=1737400, semiminor_axis=1737400,ellipse=None)
        data_crs = ccrs.SouthPolarStereo(globe=ellipsoid)
    
    # TODO: Add other projections
    
    # Create osr srs object of target srs
    dst_srs = osr.SpatialReference()
    dst_srs.ImportFromProj4(proj4str[1:-1]) # Remove the extra quotes
    dst_wkt = dst_srs.ExportToWkt() # WKT
    
    
    # Construct command prompt
    cmd = "gdalwarp -t_srs " + t_srs + \
        " -of GTiff -r near -nosrcalpha -wo SOURCE_EXTRA=1000 -dstnodata {} ".format(str(dst_nodataval)) \
        +  str(in_file) + " " + str(out_file)
    # Note: set nodata value to -9999. this is to distinguish between 
    # numeric dem raster that include points with elevation = 0.
    
    print('Reprojecting with gdalwarp\n')
    print(cmd)
    print('')
    
    # Execute the command in console (from the data_dir directory)
    p = subprocess.Popen(cmd, shell=True, cwd=str(data_dir), stderr=subprocess.PIPE)        
    # Wait until process is finished
    (output, err) = p.communicate()  
    p_status = p.wait() # This makes the wait possible
    print(err) # Print any error to screen
    
    # Close in_file and delete
    src_ds = None
    in_file.unlink()
    
    # Now, reprojected image has the original filename
    
    return

def resample_image(in_file,out_file,
                   projwin=[None,None,None,None],
                   srcwin=[None,None,None,None],
                   size=(None,None)):
    '''
    Resample and clip a raster file using the gdal_translate comand line function.

    Parameters
    ----------
    fullfilename : Pathlib
        Full filename of input raster.
    projwin : list
        Coordinates of the raster corners for clipping <ulx> <uly> <lrx> <lry>
        (in srs units)
    size : tuple
        Target raster pixel size (width,height)

    Returns
    -------
    None.

    '''
    
    # TODO: change to allow -srcwin <xoff> <yoff> <xsize> <ysize> method
    
    
    # Change the name of the input file
    # out_file = fullfilename # Output filename (original name)
    
    # Get data directory
    data_dir = in_file.parent
    
    # Open the image using gdal
    src_ds = gdal.Open(str(in_file)) # Source dataset
    src_nodataval = src_ds.GetRasterBand(1).GetNoDataValue() 
    src_ds = None # Close image
    
    # Set destination nodata value
    if src_nodataval is None:
        dst_nodataval = -9999
    else:
        dst_nodataval = src_nodataval
    
    # Copy in_file
    del_infile = False
    
    if in_file == out_file:
        # Change name of original file to in_file name (delete later)
        new_in_file = Path(in_file.parent, 'infile_' + in_file.stem + in_file.suffix)
        in_file.rename(new_in_file) # Rename file
        in_file = new_in_file       # Rename variable
        del_infile = True # Flag to delete temp infile
    
    # Convert projwin and size to strings
    if projwin==[None,None,None,None]:
        # No subsetting
        projwin_str = ''
    else:
        # TODO: add ' -projwin ' to start 
        # projwin_str = '{:s}'.format(' '.join(['{:.5f}'.format(x) for x in projwin]))
        projwin_str = ' -projwin {:s}'.format(' '.join(['{:.5f}'.format(x) for x in projwin]))
    
        
    # Size string
    if size == (None,None):
        # No resample
        size_str = ''
    else:
        # size_str = '{:s}'.format(' '.join(['{:d}'.format(x) for x in size]))
        size_str = ' -outsize {:s}'.format(' '.join(['{:d}'.format(x) for x in size]))
    
    # Construct command prompt
    # cmd = "gdal_translate -projwin " + projwin_str + " -outsize " + size_str + \
    #     " -of GTiff -r near -a_nodata -9999 " \
    #     +  str(in_file) + " " + str(out_file)
    
    cmd = "gdal_translate" + projwin_str + size_str + \
        " -of GTiff -r near -a_nodata {} ".format(str(dst_nodataval)) \
        +  str(in_file) + " " + str(out_file)
    
    print('Resampling to target extent and resolution using gdal_translate\n')
    print(cmd)
    print('')
    
    
    # Execute the command in console (from the data_dir directory)
    p = subprocess.Popen(cmd, shell=True, cwd=str(data_dir), stderr=subprocess.PIPE)        
    # Wait until process is finished
    (output, err) = p.communicate()  
    p_status = p.wait() # This makes the wait possible
    print(err) # Print any error to screen
    
    # Close in_file and delete
    src_ds = None
    
    if del_infile == True:
        in_file.unlink()
    
    return

#%% Rasterizing Shapefiles ----------------------------------------------------
    
def rasterize_layer_match_raster(shape_file, dst_file, match_raster_file):
    '''
    Convert a vector shapefile to a raster file matching the extent and resolution
    of a specified file.

    See Listing 11.10 (pg 264) of Manning Geoprocessing with Python 
    See also: https://gis.stackexchange.com/questions/212795/rasterizing-shapefiles-with-gdal-and-python
    

    Parameters
    ----------
    shape_file : TYPE
        DESCRIPTION.
    dst_file : TYPE
        DESCRIPTION.
    match_raster_file : TYPE
        DESCRIPTION.

    '''
    
    # Convert a vector shapefile to a raster file matching the extent and resolution
    # of a specified file.
    # See Listing 11.10 (pg 264) of Manning Geoprocessing with Python 
    # See also: https://gis.stackexchange.com/questions/212795/rasterizing-shapefiles-with-gdal-and-python
    
    # Open match_raster_file and get extent and resolution
    # Open the image using gdal (allowing update)
    src_ds = gdal.Open(str(match_raster_file),gdal.GA_ReadOnly) # Source dataset
    geo_transform = src_ds.GetGeoTransform() # Get geotransform
    proj_wkt = src_ds.GetProjection() # Projection
    x_min = geo_transform[0]
    y_max = geo_transform[3]
    x_max = x_min + geo_transform[1] * src_ds.RasterXSize
    y_min = y_max + geo_transform[5] * src_ds.RasterYSize
    x_res = src_ds.RasterXSize
    y_res = src_ds.RasterYSize
    pixel_width = geo_transform[1]
    src_ds = None # Close dataset
    
    # Open the shapefile and read data
    vector_ds = ogr.Open(str(shape_file), gdal.GA_ReadOnly)
    layer = vector_ds.GetLayer() # Get the vector layer
    
    
    # Create target dataset
    target_ds = gdal.GetDriverByName('GTiff').Create(str(dst_file), x_res, y_res, 1, gdal.GDT_Byte)
    target_ds.SetGeoTransform((x_min, pixel_width, 0, y_min, 0, pixel_width))
    target_ds.SetProjection(proj_wkt)
    
    band = target_ds.GetRasterBand(1)
    NoData_value = -9999
    band.SetNoDataValue(NoData_value)
    band.FlushCache()
    # gdal.RasterizeLayer(target_ds, [1], layer, options=["ATTRIBUTE=hedgerow"])
    gdal.RasterizeLayer(target_ds, [1], layer)
    
    target_ds = None # Close target dataset
    
    
    
    # # Create empty raster dataset to store data
    # tif_driver = gdal.GetDriverByName('GTiff')
    # dst_ds = tif_driver.Create(dst_filename,cols,rows) # Create dataset
    # # dst_ds.SetProjection()
    # dst_ds.SetGeoTransform() 
    
    
    return


#%% GDAL DEM Calculations -----------------------------------------------------

# Wrapper functions to execute gdaldem command line functions.
# https://gdal.org/programs/gdaldem.html
# gdaldem <mode> <input> <output> <options>
#
# Modes:
# - hillshade : Generate a shaded releif map
# - slope : Generate a slope map
# - aspect : Generate an aspect map indicating azimuth
# - color-relief : Color relief map
# - TRI : Generate a Terrain Ruggedness Index (TRI) map
# -

# - 

def slope_from_dem(input_dem, output_slope_map,scale=1):
    '''
    Generate a slope map from a GDAL-supported elevation raster using GDALDEM 
    command line functions:
    
    gdaldem slope input_dem output_slope_map
        [-p use percent slope (default=degrees)] [-s scale* (default=1)]
        [-alg ZevenbergenThorne]
        [-compute_edges] [-b Band (default=1)] [-of format] [-co "NAME=VALUE"]* [-q]
    
    Parameters
    ----------
    input_dem : TYPE
        DESCRIPTION.
    output_slope_map : TYPE
        DESCRIPTION.

    '''
    
    # 
    
    # Get directory of input file
    infiledir = input_dem.parent
    
    # Get the filenames
    infile = input_dem.name
    outfile = output_slope_map.name
    
    
    
    # Construct gdal call

    # Flags to use
    # -compute_edges : Do the computation at raster edges and near nodata values
    
    # Optional
    # -s : TODO. If input dem is in lat/long, need to set a scale.
    # -alg ZevenbergenThorne : different method better suited to smooth terrain (dont use)
    
    
    # Construct command prompt
    cmd = "gdaldem slope " +  infile + " " + outfile + \
          " -s " + str(scale) + \
          " -compute_edges -of GTiff"
        
    # Execute command
    print('\nCreating slope map with gdaldem\n')
    print(cmd)
    print('')
    
    # Execute the command in console
    p = subprocess.Popen(cmd, shell=True, cwd=str(infiledir),stderr=subprocess.PIPE)        
    # Wait until process is finished
    (output, err) = p.communicate()  
    p_status = p.wait() # This makes the wait possible
    print(err) # Print any error to screen
    
    
    return

def roughness_from_dem(input_dem, output_roughness_map):
    '''
    Generate a slope map from a GDAL-supported elevation raster using GDALDEM 
    command line functions:
    
    gdaldem roughness input_dem output_roughness_map
            [-compute_edges] [-b Band (default=1)] [-of format] [-q]
    
    Parameters
    ----------
    input_dem : TYPE
        DESCRIPTION.
    output_roughness_map : TYPE
        DESCRIPTION.

    '''
    
    # 
    
    # Get directory of input file
    infiledir = input_dem.parent
    
    # Get the filenames
    infile = input_dem.name
    outfile = output_roughness_map.name
    
    
    # Construct gdal call

    # Flags to use
    # -compute_edges : Do the computation at raster edges and near nodata values
    
    # Optional
    # -s : TODO. If input dem is in lat/long, need to set a scale.
    # -alg ZevenbergenThorne : different method better suited to smooth terrain (dont use)
    
    
    # Construct command prompt
    cmd = "gdaldem roughness " +  infile + " " + outfile + \
          " -compute_edges -of GTiff"
        
    # Execute command
    print('\nCreating roughness map with gdaldem\n')
    print(cmd)
    print('')
    
    # Execute the command in console
    p = subprocess.Popen(cmd, shell=True, cwd=str(infiledir),stderr=subprocess.PIPE)        
    # Wait until process is finished
    (output, err) = p.communicate()  
    p_status = p.wait() # This makes the wait possible
    print(err) # Print any error to screen
    
    
    return


#%% GDAL Proximity Calculations -----------------------------------------------

# Wrappers for proximity calculations using gdal_proximity.py
# Also other modules (GRASS, ...)

def proximity_from_source(input_raster, output_proximity_map, 
                          of='GTiff',
                          distunits='PIXEL',
                          srcband=None,
                          values=None,
                          maxdist = None,
                          nodata = None,
                          ):
    '''
    Generate a proximity map from a GDAL-supported raster using gdal_proximity.py
    command line functions:
    
    gdal_proximity.py <srcfile> <dstfile> [-srcband n] [-dstband n]
                  [-of format] [-co name=value]*
                  [-ot Byte/UInt16/UInt32/Float32/etc]
                  [-values n,n,n] [-distunits PIXEL/GEO]
                  [-maxdist n] [-nodata n] [-use_input_nodata YES/NO]
                  [-fixed-buf-val n]
    
    Parameters
    ----------
    input_raster : TYPE
        DESCRIPTION.
    output_proximity_map : TYPE
        DESCRIPTION.

    '''
    
    # Get directory of input file
    infiledir = input_raster.parent
    
    # Get the filenames
    infile = input_raster.name
    outfile = output_proximity_map.name
    
    # Construct command prompt
    cmd = "gdal_proximity.py " +  infile + " " + outfile + " -of " + of
    # Add additional arguments
    if distunits is not None:
        # Distance units ('PIXEL' or 'GEO')
        cmd = cmd + " -distunits " + distunits
    
    if srcband is not None:
        # Source band
        cmd = cmd + " -srcband " + str(srcband)
        
    if values is not None:
        # Values
        cmd = cmd + " -values " + values
    
    if maxdist is not None:
        # Maximum distance
        cmd = cmd + " -maxdist " + str(maxdist)
    
    if nodata is not None:
        # Nodata value
        cmd = cmd + " -nodata " + str(nodata)
    
    
    # Execute command
    print('\nCreating roughness map with gdaldem\n')
    print(cmd)
    print('')
    
    # Execute the command in console
    p = subprocess.Popen(cmd, shell=True, cwd=str(infiledir),stderr=subprocess.PIPE)        
    # Wait until process is finished
    (output, err) = p.communicate()  
    p_status = p.wait() # This makes the wait possible
    print(err) # Print any error to screen
    
    return



#%% Mesh Generateion ----------------------------------------------------------
# Move to mesh_utils?


