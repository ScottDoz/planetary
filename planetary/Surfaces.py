# -*- coding: utf-8 -*-
"""
Created on Fri Apr 23 20:26:20 2021

@author: scott

Planetary Surfaces

Classes for representing objects on planetary surfaces.
Region models containing GIS data
Terrain Models

"""

# Standard imports
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
import json
import requests
from pprint import pprint
import os
import sys
import subprocess
from pathlib import Path
import ast
import json

# GEO processing packages
from owslib.wms import WebMapService
from osgeo import gdal, osr
import cartopy.crs as ccrs
import pyproj

# Plotting packages
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable, axes_size
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
# %matplotlib widget
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib as mpl

import pdb

# Module imports
from planetary.mesh_utils import *
from planetary.utils import append_df_to_excel, get_data_home
from planetary.gis_tools import tif_from_wms, scale_dem_raster


# Set data dir
DATA_DIR = get_data_home()


#%% ###########################################################################
#                           Planetary Region
# #############################################################################

class PlanetaryRegion:
    '''
    Class containing a collection of GIS data layers covering a defined region
    on a planetary surface.
    
    This class contains 
    - attibutes listing details of the included data layers;
    - methods for generating and processing new data layers; and
    - methods of extracting data from individual raster files.

    
    Region name, extent, and available rasters are defined from an xls config file.
    
    Methods:
    - generate raster files from WMS.
    - explore contents of available data
    - get info on raster files included in the model
    - generate GIS maps in cartopy
    - (future) generate a QGIS project of the region
    
    '''
    
    def __init__(self, fullfilename):
        '''
        Instantiate PlanetaryRegion class from an xlsx file.
        Read in extent from config file.
        '''
        
        # Attributes
        self.name = None     # Name of the region (string)
        self.planet = None   # Parent planet (string)
        self.longlat_proj4 = None 
        self.configfile = None # Filename of contents
        self.data_dir = None # Data directory
        
        self.lat0 = None     # Central latitude (deg N)
        self.lat_min = None  # Minimum latitude (deg N)
        self.lat_max = None  # Minimum latitude (deg N)
        self.long0 = None    # Central longitude (deg E)
        self.long_min = None # Minimum longitude (deg E)
        self.long_max = None # Minimum longitude (deg E)
        self.bbox = None     # Bounding box (Left, bottom, right, top) = 
                             #  (long_min,lat_min,long_max,lat_max) 
        self.layers = []     # List of available layers
        self.rasters = []    # List of available raster files
        self.terrain = None  # PlanetaryTerrain object
        self.craters = None  # List of craters
        
        # Split full filename to get filename and path of config file
        self.configfile = fullfilename # Config file name
        
        # Extent Details ----------------------------------------- 
        
        # Read json file
        with open(fullfilename, 'r') as file:
            raw_content = file.read()
            data = json.loads(raw_content)
        
        # Extract region name and planet name
        self.name = data['Description']['region_name']
        self.planet =  data['Description']['planet']
        
        # Extract data directory
        data_dir = DATA_DIR / data['Description']['data_dir']
        self.data_dir = data_dir.resolve()
        
        # Extract extent data
        if 'lat_min' in data['Extent'].keys():
            # Method 1: From Bounding box
            lat_min = data['Extent']['lat_min']
            lat_max = data['Extent']['lat_max']
            long_min = data['Extent']['long_min']
            long_max = data['Extent']['long_max']
            bbox_srs = data['Extent']['bbox_srs']
            self.lat_min = lat_min
            self.lat_max = lat_max
            self.long_min = long_min
            self.long_max = long_max
            self.bbox = (long_min,lat_min,long_max,lat_max, bbox_srs) 
        
        elif 'location' in data['Extent'].keys():
            # Method 2: From location + range
            location = data['Extent']['location']
            lat_range = data['Extent']['lat_range']
            long_range = data['Extent']['long_range']
            
            # Convert location string to tuple
            location = location.replace('[','').replace(']','').replace('(','').replace(')','')
            location = tuple(map(float, location.split(',')))
            
            # Check if location is a tuple
            if len(location) != 2:
                pdb.set_trace()
                raise ValueError('Error in location. Expect tuple [lat0,long0].') 
            
            if np.isnan(lat_range):
               raise ValueError('Error in lat_range.') 
            
            if np.isnan(long_range):
               raise ValueError('Error in long_range.') 
            
            # Get lat0,long0 from location
            lat0 = location[0]
            long0 = location[1]
            
            # Set extent attributes
            self.lat_min = lat0 - abs(lat_range)
            self.lat_max = lat0 + abs(lat_range)
            self.long_min = long0 - abs(long_range)
            self.long_max = long0 + abs(long_range)
            self.bbox = (long_min,lat_min,long_max,lat_max)

        # Create geodataframe of bounding box (EPSG:4326) 
        self.bbox_geom = self._create_bbox_geometry()
        # self.bbox_geom = shapely.geometry.box(*self.bbox) # minx,miny,maxx,maxy
        
        # # From xlsx --------------------------------------------------
        # # Read details from the 'Extent' sheet
        # try:
        #     dfExtent = pd.read_excel(fullfilename,sheet_name='Extent')
        # except:
        #     dfExtent = pd.read_excel(fullfilename,sheet_name='Extent', engine='openpyxl')

        # # Extract region name and planet name
        # self.name = dfExtent['Value'][dfExtent.Variable == 'region_name'].iloc[0]
        # self.planet = dfExtent['Value'][dfExtent.Variable == 'planet'].iloc[0]
        
        # # Extract data directory
        # data_dir = DATA_DIR / dfExtent['Value'][dfExtent.Variable == 'data_dir'].iloc[0] # Data directory
        # self.data_dir = data_dir.resolve()
        
            
        
        # # From bounding box
        # lat_min = dfExtent['Value'][dfExtent.Variable == 'lat_min'].iloc[0]
        # lat_max = dfExtent['Value'][dfExtent.Variable == 'lat_max'].iloc[0]
        # long_min = dfExtent['Value'][dfExtent.Variable == 'long_min'].iloc[0]
        # long_max = dfExtent['Value'][dfExtent.Variable == 'long_max'].iloc[0]
        # bbox_srs = dfExtent['Value'][dfExtent.Variable == 'bbox_srs'].iloc[0]
        
        
        # # From location and range
        # location = dfExtent['Value'][dfExtent.Variable == 'location'].iloc[0]
        # lat_range = dfExtent['Value'][dfExtent.Variable == 'lat_range'].iloc[0]
        # long_range = dfExtent['Value'][dfExtent.Variable == 'long_range'].iloc[0]
        
        # # Resolve Extent input method
        
        # # Method 1: From bounding box
        # if ~np.isnan(lat_min):
        #     # lat_min has been defined
            
        #     # Check if one or more of the variables have not been defined
        #     if np.nan in [lat_min,lat_max,long_min,long_max]:
        #         raise ValueError('Error in extent. One or more bounds not defined.')
        
        #     # Set extent attributes
        #     self.lat_min = lat_min
        #     self.lat_max = lat_max
        #     self.long_min = long_min
        #     self.long_max = long_max
        #     self.bbox = (long_min,lat_min,long_max,lat_max, bbox_srs) 
            
        # # Method 2: From location + range
        # else:
        #     # location has been defined
        #     # Convert location string to tuple
        #     location = location.replace('[','').replace(']','').replace('(','').replace(')','')
        #     location = tuple(map(float, location.split(',')))
            
        #     # Check if location is a tuple
        #     if len(location) != 2:
        #         pdb.set_trace()
        #         raise ValueError('Error in location. Expect tuple [lat0,long0].') 
            
        #     if np.isnan(lat_range):
        #        raise ValueError('Error in lat_range.') 
            
        #     if np.isnan(long_range):
        #        raise ValueError('Error in long_range.') 
            
        #     # Get lat0,long0 from location
        #     lat0 = location[0]
        #     long0 = location[1]
            
        #     # Set extent attributes
        #     self.lat_min = lat0 - abs(lat_range)
        #     self.lat_max = lat0 + abs(lat_range)
        #     self.long_min = long0 - abs(long_range)
        #     self.long_max = long0 + abs(long_range)
        #     self.bbox = (long_min,lat_min,long_max,lat_max)
        
        # # Create geodataframe of bounding box (EPSG:4326) 
        # self.bbox_geom = self._create_bbox_geometry()
        # # self.bbox_geom = shapely.geometry.box(*self.bbox) # minx,miny,maxx,maxy
        
        
        
        
        # Append list of available layers -------------------------------------
        dfWMS = self.list_wms_layers()
        dfRasters = self.list_raster_layers()
        dfShapes = self.list_shapefile_layers()
        dfComp = self.list_computed_layers()
        dfLayers = self.list_all_layers()
        
        self.layers = list(dfLayers.layer_name)
        self.rasters = list(dfLayers.filename)
        self.shapes = list(dfShapes.filename)
        
        # Set latlon srs of planet
        if self.planet in ['Luna','Moon']:
            # IAU2000:30100
            self.longlat_proj4 = '+proj=longlat +a=1737400 +b=1737400 +no_defs '
        elif self.planet in ['Mars']:
            # IAU2000:49900
            self.longlat_proj4 = '+proj=longlat +a=3396190 +b=3376200 +no_defs '
        else:
            # TODO: add for other planets
            self.longlat_proj4 = None
        
        
    def _create_bbox_geometry(self):
        ''' Create a shapely polygon of the bounding box '''
        
        num_points_x = 10 # Number of points along x direction
        num_points_y = 10 # Number of points along y direction
        
        # Top of box
        top_points = np.zeros([num_points_x,2]) # Initialize points
        top_points[:,0] = np.linspace(self.long_min,self.long_max,num_points_x)
        top_points[:,1] = np.ones(num_points_x)*self.lat_max   
        
        # Right of box
        right_points = np.zeros([num_points_y,2]) # Initialize points
        right_points[:,0] = np.ones(num_points_y)*self.long_max   
        right_points[:,1] = np.linspace(self.lat_max,self.lat_min,num_points_y)
        
        # Bottom of box
        bottom_points = np.zeros([num_points_x,2]) # Initialize points
        bottom_points[:,0] = np.linspace(self.long_max,self.long_min,num_points_x)
        bottom_points[:,1] = np.ones(num_points_x)*self.lat_min   
        
        # Left of box
        left_points = np.zeros([num_points_y,2]) # Initialize points
        left_points[:,0] = np.ones(num_points_y)*self.long_min   
        left_points[:,1] = np.linspace(self.lat_min,self.lat_max,num_points_y)
        
        # Combine
        points = np.concatenate([top_points[:-1],right_points[:-1],bottom_points[:-1],left_points[:-1]])
        points_list = list(zip(list(points[:,0]),list(points[:,1])))
        
        
        return shapely.geometry.Polygon(points_list)

    
    # Content listing methods -------------------------------------------------
    
    def list_all_layers(self):
        '''
        List the details of all available raster layers from both
        - WMS-derived raster layers; and
        - extenal located raster files.

        Returns
        -------
        dfWMS : Pandas dataframe
            Dataframe containing details of WMS-derived rasters.

        '''
        
        # Get list of WMS layers
        dfWMS = self.list_wms_layers()
        # Rename 'wms_url' column to 'source'
        dfWMS = dfWMS.rename(columns={'wms_url':'source'})
        
        # Get list of saved raster files
        dfRasters = self.list_raster_layers()
        
        # Get list of computed raster files
        dfcomp =  self.list_computed_layers()
        
        # Join the lists
        cols = ['layer_name','filename','filepath','source','pixel_size']
        dfLayers = pd.concat([dfWMS[cols],dfRasters[cols],dfcomp[cols]],ignore_index=True)
        
        
        return dfLayers
    
    def list_wms_layers(self):
        '''
        List the details of WMS-derived raster layers. 

        Returns
        -------
        dfWMS : Pandas dataframe
            Dataframe containing details of WMS-derived rasters.

        '''
        
        # Read contents from the 'WMS' sheet
        if self.configfile.suffix == '.xlsx':
            # Config file is excel sheet
            try:
                dfWMS = pd.read_excel(self.configfile,sheet_name='WMS')
            except:
                dfWMS = pd.read_excel(self.configfile,sheet_name='WMS',engine='openpyxl')
        
        elif self.configfile.suffix == '.json':
            # Config file is json
            
            # Read json data
            with open(str(self.configfile), 'r') as file:
                raw_content = file.read()
                data = json.loads(raw_content)
                
            dfWMS = pd.DataFrame(data['WMS'])
        
        # Add filepath column
        dfWMS['filepath'] = self.data_dir
        
        # Check if each wms layer has been created
        dfWMS['exists'] = False
        # Loop through files and check if file has been created
        for i, row in dfWMS.iterrows():
            # Extract details
            wmsfilename = row.filename
            if pd.isnull(dfWMS['filename'].iloc[i])==False:
                wmsfullfilename = self.data_dir / wmsfilename
                # Update existance status
                dfWMS['exists'].iloc[i] = wmsfullfilename.is_file()
        
        # return WMS details
        return dfWMS
    
    def list_raster_layers(self):
        '''
        List the filenames and locations of raster files to include in the
        region model.

        Returns
        -------
        dfRasters : Pandas dataframe
            Dataframe containing details of WMS-derived rasters.

        '''
        
        if self.configfile.suffix == '.xlsx':
            # Config file is excel sheet
            # Read contents from the 'Raster' sheet
            try:
                dfRasters = pd.read_excel(self.configfile,sheet_name='Raster')
            except:
                dfRasters = pd.read_excel(self.configfile,sheet_name='Raster',engine='openpyxl')
        
        elif self.configfile.suffix == '.json':
            # Config file is json
            
            # Read json data
            with open(str(self.configfile), 'r') as file:
                raw_content = file.read()
                data = json.loads(raw_content)
                
            dfRasters = pd.DataFrame(data['Raster'])
            
            # Add columns for empty array
            if dfRasters.empty:
                dfRasters = pd.DataFrame(columns=['layer_name','layer_type','filename','filepath','source','reference'])

        
        dfRasters['pixel_size'] = ''
        
        
        # Drop any empty rows
        dfRasters = dfRasters.dropna(how='all',
                         subset=['layer_name','layer_type','filename','filepath','source','reference'])
        
        # Convert filepath to pathlib object
        for i, row in dfRasters.iterrows():
            try:
                file_data_dir = DATA_DIR / row['filepath'] # Data directory
            except:
                pdb.set_trace()
            file_data_dir = file_data_dir.resolve()
            # Reset value in dataframe
            dfRasters['filepath'].iloc[i] = file_data_dir
        
        # Read pixelsize of each raster
        for i, row in dfRasters.iterrows():
            # Get full filename
            fullfilename = row.filepath / row.filename
            # Open file
            ds = gdal.Open(str(fullfilename))
            pixel_size = (ds.RasterXSize,ds.RasterYSize)
            # dfRasters['pixel_size'].iloc[i] = pixel_size
            dfRasters.at[i, 'pixel_size'] = pixel_size
            
            # Close file
            ds = None
            
        
        return dfRasters
    
    def list_computed_layers(self):
        '''
        List the details of computed raster layers. 

        Returns
        -------
        dfComp : Pandas dataframe
            Dataframe containing details of computed rasters.

        '''
        
       # # Read contents from the 'Raster' sheet
       #  try:
       #      dfComp = pd.read_excel(self.configfile,sheet_name='Computed')
       #  except:
       #      dfComp = pd.read_excel(self.configfile,sheet_name='Computed',engine='openpyxl')
       #  dfComp['pixel_size'] = ''
        
        if self.configfile.suffix == '.xlsx':
            # Config file is excel sheet
            # Read contents from the 'Raster' sheet
            try:
                dfComp = pd.read_excel(self.configfile,sheet_name='Computed')
            except:
                dfComp = pd.read_excel(self.configfile,sheet_name='Computed',engine='openpyxl')
        
        elif self.configfile.suffix == '.json':
            # Config file is json
            
            # Read json data
            with open(str(self.configfile), 'r') as file:
                raw_content = file.read()
                data = json.loads(raw_content)
                
            dfComp = pd.DataFrame(data['Computed'])
            
            # Add columns for empty array
            if dfComp.empty:
                dfComp = pd.DataFrame(columns=['layer_name','layer_type','filename','filepath','source','reference'])

        dfComp['pixel_size'] = ''
        
        # Convert filepath to pathlib object
        for i, row in dfComp.iterrows():
            if pd.isnull(dfComp['filename'].iloc[i])==False:
                file_data_dir = DATA_DIR / row['filepath'] # Data directory
                file_data_dir = file_data_dir.resolve()
                # Reset value in dataframe
                dfComp['filepath'].iloc[i] = file_data_dir
        
        # Read pixelsize of each raster
        for i, row in dfComp.iterrows():
            if pd.isnull(dfComp['filename'].iloc[i])==False:
                # Get full filename
                fullfilename = row.filepath / row.filename
                # Open file
                try:
                    ds = gdal.Open(str(fullfilename))
                    pixel_size = (ds.RasterXSize,ds.RasterYSize)
                    # dfComp['pixel_size'].iloc[i] = pixel_size
                    dfComp.at[i, 'pixel_size'] = pixel_size
                except:
                    pdb.set_trace()
            
                # Close file
                ds = None
        
        
        # return WMS details
        return dfComp
    
    def list_shapefile_layers(self):
        '''
        List the filenames and locations of shapefile files to include in the
        region model.

        Returns
        -------
        dfShapes : Pandas dataframe
            Dataframe containing details of WMS-derived rasters.

        '''
        
        # # Read contents from the 'Raster' sheet
        # try:
        #     dfShapes = pd.read_excel(self.configfile,sheet_name='Shapefile')
        # except:
        #     dfShapes = pd.read_excel(self.configfile,sheet_name='Shapefile',engine='openpyxl')
        
        
        if self.configfile.suffix == '.xlsx':
            # Config file is excel sheet
            # Read contents from the 'Shapefile' sheet
            try:
                dfShapes = pd.read_excel(self.configfile,sheet_name='Shapefile')
            except:
                dfShapes = pd.read_excel(self.configfile,sheet_name='Shapefile',engine='openpyxl')
        
        elif self.configfile.suffix == '.json':
            # Config file is json
            
            # Read json data
            with open(str(self.configfile), 'r') as file:
                raw_content = file.read()
                data = json.loads(raw_content)
                
            dfShapes = pd.DataFrame(data['Shapefile'])
            
            # Add columns for empty array
            if dfShapes.empty:
                dfShapes = pd.DataFrame(columns=['layer_name','layer_type','filename','filepath','source','reference'])

        
        # Convert filepath to pathlib object
        for i, row in dfShapes.iterrows():
            if pd.isnull(dfShapes['filename'].iloc[i])==False:
                file_data_dir = DATA_DIR / row['filepath'] # Data directory
                file_data_dir = file_data_dir.resolve()
                # Reset value in dataframe
                dfShapes['filepath'].iloc[i] = file_data_dir
        
        
        return dfShapes
    
    # Shapefile Methods -------------------------------------------------------
    
    def list_craters(self):
        '''
        List craters

        Returns
        -------
        dfcraters : TYPE
            DESCRIPTION.

        '''
        
        if self.planet in ['Luna','Moon']:
            # Get Lunar Crater Database
            # gdf = LunarCraterDB.import_moon_craters_LU78287GT()
            gdf = LunarCraterDB.import_moon_craters_robbins()
            # Find subset of craters in bbox
            bbox_df = gpd.GeoDataFrame(gpd.GeoSeries(self.bbox_geom), columns=['geometry'])
            dfcraters = gpd.overlay(gdf, bbox_df, how='intersection')
            
            self.dfcraters = dfcraters
        
        elif self.planet in ['Mars']:
            # Get Mars Crater Database
            # gdf = LunarCraterDB.import_mars_craters_MA132843GT()
            gdf = LunarCraterDB.import_mars_craters_robbins()
            
            # Find subset of craters in bbox
            bbox_df = gpd.GeoDataFrame(gpd.GeoSeries(self.bbox_geom), columns=['geometry'])
            dfcraters = gpd.overlay(gdf, bbox_df, how='intersection')
            
        else:
            # TODO: Add other crater databases
            
            self.dfcraters = None
        
        
        return dfcraters
    
    
    
    # Raster Generation Methods -----------------------------------------------
    # The following methods automate the generation of raster files.
    
    def generate_wms_rasters(self,update=False):
        '''
        Generate tif files for the requrested WMS layers in config file.

        Parameters
        ----------
        update : Boolean, optional
            Flag to specify if existing files are to be overwritten. 
            The default is False.

        '''
        
        # Get list of WMS layers
        dfWMS = self.list_wms_layers()
        
        # Instantiate wms dictionary
        wms_dict = pd.DataFrame(columns=['wms_name','wms'])
        
        # Loop through files and check if file has been created
        for i, row in dfWMS.iterrows():
            
            # Get existance status fo tif file
            exists = row.exists
            
            if (exists == False) or (update == True):
                # File does not exist (or, request new version)
                # Generate raster file of wms layer.
                
                # Extract extent details
                bbox = self.bbox
                
                # Extract details of layer
                wms_name = row.wms_name
                wms_url = row.wms_url
                wms_version = row.wms_version
                layer_name = row.layer_name
                s_srs = row.s_srs
                t_srs = row.t_srs
                size = tuple(int(x) for x in row.pixel_size.strip('()').split(','))
                filename = row.filename
                try:
                    kwargs = ast.literal_eval(row.kwargs) 
                except:
                    kwargs = {}
                    
                
                
                # Create wms connection
                if (len(wms_dict)>0) & (wms_name in list(wms_dict['wms_name'])):
                    # WMS connection already made - extract from dataframe
                    wms = wms_dict['wms'][wms_dict.wms_name == wms_name].iloc[0]
                else:
                    # Create new wms connection
                    print('\nConnecting to WMS: {}\n'.format(wms_url))
                    wms = WebMapService(url=wms_url, version=wms_version)
                    # Append wms connection to wms_dict
                    # wms_dict['wms_name'] = wms_name
                    # wms_dict['wms'] = wms
                    # wms_dict = wms_dict.append({'wms_name':wms_name,'wms':wms} , ignore_index=True)
                    wms_dict = pd.concat([wms_dict , pd.DataFrame({'wms_name':[wms_name],'wms':[wms]})], ignore_index=True)
                
                # TODO: Add wms connection to a dict to prevent mutliple loadings
                # Append 
                
                
                # Generate raster from wms 
                tif_from_wms(wms=wms,layers=[layer_name],s_srs=s_srs, bbox=bbox,
                             size=size,format='image/tiff', # Required arguments
                             t_srs=t_srs, # Target srs projection (srs string)
                             styles=None, transparent=True,bgcolor=None,method=None, # Optional arguments
                             filename=filename,data_dir=self.data_dir,
                             planet=self.planet, **kwargs)
                
                
                # Fix numeric dtm
                if layer_name == 'luna_wac_dtm_numeric':
                    # Input elevation data is in km. Convert to m
                    scale_dem_raster(self.data_dir/filename,1000)
                    
                
            
            else:
                # File exists. Skip to next wms layer.
                pass
        
        return
    
    def resample_raster(self, infile, outfile,
                        size=(None,None),
                        srcwin=[None,None,None,None],
                        projwin=[None,None,None,None]):
        # TODO: Generate a new raster by resample or subset a raster.
        
        # Resampling:
        # -tr <xres> <yres> target resolution
        
        # Subsetting:
        # -srcwin <xoff> <yoff> <xsize> <ysize> or
        # -projwin <ulx> <uly> <lrx> <lry>
        
        
        # Check if infile is found
        if infile not in self.rasters + self.layers:
            raise ValueError('{} infile raster not found.'.format(demfile))
        
        # Load list of all layers
        dfLayers = self.list_all_layers()
        
        # Get the filepath
        inpath = dfLayers['filepath'][dfLayers.filename == infile].iloc[0]
        
        # Get fullfilename of input dem
        in_file = inpath/infile
        
        # Get fullfilename of output raster
        # (Store new file in Region folder)
        out_file = self.data_dir / outfile
        
        # Parse inputs to resample_image function
        from planetary.gis_tools import resample_image
        resample_image(in_file,out_file,
                       projwin=projwin, srcwin=srcwin, size=size)
        
        # Add the new file to raster sheet of the config file
        dfrasters = self.list_raster_layers()
        
        filename = out_file.name
        
        # Add new file to config file
        if filename not in list(dfrasters.filename):
            startrow = len(dfrasters) + 1 # (add row for header and one for new row)
            filepath = out_file.parent
            filepath = str(Path('../Data/'+str(filepath).split('Data')[1]))
            source = 'Resampled from ' + in_file.name 
            row_dict = {'id':np.nan,
                        'layer_name': out_file.stem, 
                        'layer_type':'',
                        'filename': out_file.name,
                        'filepath': filepath,
                        'source': source,
                        'reference':'',
                        }
            df = pd.DataFrame([row_dict])
            append_df_to_excel(str(self.configfile), df, sheet_name='Raster', 
                                header=None, startrow=startrow, index=False)

        # Update list of raster and layers
        dfLayers = self.list_all_layers()
        self.layers = list(dfLayers.layer_name)
        self.rasters = list(dfLayers.filename)
        
        
        return
    
    
    def generate_dem_products(self, demfile, methods=['slope','aspect','TRI','roughness']):
        
    
        # Use GDALDEM methods to process an input dem raster to produce derrived maps.
        
        # Methods include:
        # 'hillshade':
        # 'slope' :
        # 'aspect' :
        # 'color-relief' :
        # 'TRI' :
        # 'TPI' :
        # 'roughness' :
    
        # Wrapper functions for each method are defined in gis_tools.py
    
    
        # Check if file is found
        if demfile not in self.rasters + self.layers:
            raise ValueError('{} dem raster not found.'.format(demfile))
        
        # Load list of all layers
        dfLayers = self.list_all_layers()
        
        # Get the filepath
        dempath = dfLayers['filepath'][dfLayers.filename == demfile].iloc[0]
        
        # Get fullfilename of input dem
        input_dem = dempath/demfile
        
        
        # Check the elevation units of the raster (m or km)
        
        # Check the units of the elevation data
        ds = gdal.Open(str(input_dem))
        dem_max = ds.GetRasterBand(1).ReadAsArray().max()
        dem_min = ds.GetRasterBand(1).ReadAsArray().min()
        dem_range = dem_max - dem_min
        
        # Get Proj4
        # Projection in WKT
        proj_wkt = ds.GetProjection()
        # e.g. 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST],AUTHORITY["EPSG","4326"]]'
        # Note: WGS84 = EPSG4326 = PlateCarree
        # FIXME: No projection info when using reprojection with python bindings.
        # Convert projection to osr SpatialReference object
        inproj = osr.SpatialReference()
        inproj.ImportFromWkt(proj_wkt)
        # Proj4 string
        proj4_str = inproj.ExportToProj4()
        s_srs = f'"{proj4_str}"'
        # Get input raster size
        width = ds.RasterXSize
        height = ds.RasterYSize
        ds = None
        
        # FIXME: Set scale based on assumed units of dem
        if dem_range > 100.:
            # Elevation is likely in m
            scale = 1
        else:
            # Elevation is likely in km
            scale = 1/1000.
        
        # If DEM is in lat/long, reproject into orthogonal --------------------
        
        if 'proj=longlat' in proj4_str:
            # Input file is lat/long. Project to orthograthic
            
            # Set newfilename of temporary tif
            tempdemfile = 'temp_dem.tif'
            tempdemfilename = str(Path(dempath) / tempdemfile)
            temp_input_dem = Path(dempath)/tempdemfile
            
            if temp_input_dem.exists():
                temp_input_dem.unlink() # Delete file if it exists
            
            # Target Projection Proj4 string
            t_srs = r'"+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs"'
            
            # Construct command prompt
            cmd = "gdalwarp -t_srs " + t_srs + \
                " -of GTiff -r near -nosrcalpha -wo SOURCE_EXTRA=1000 -dstnodata -9999 " \
                + '-ts ' + str(width) + ' ' + str(height) + ' ' \
                +  demfile + " " + tempdemfilename

            print('Reprojecting with gdalwarp\n')
            print(cmd)
            print('')
            
            # Execute the command in console
            p = subprocess.Popen(cmd, shell=True, cwd=str(dempath) ,stderr=subprocess.PIPE)
            # Wait until process is finished
            (output, err) = p.communicate()
            p_status = p.wait() # This makes the wait possible
            print(err) # Print any error to screen

        
        
        # Loop through requested methods --------------------------------------
        # pdb.set_trace()
        
        # Hillshade
        if 'hillshade' in methods:
            # TODO
            pass
        
        # DEM Slope
        if 'slope' in methods:
            # Get fullfilename of output dem
            output_slope_map = input_dem.parent/(input_dem.stem + '_slope' + input_dem.suffix)
            
            # Call wrapper function from gis_tools.py
            from planetary.gis_tools import slope_from_dem
            if 'proj=longlat' in proj4_str:
                # Run on re-projected dem
                temp_output_slope_map = temp_input_dem.parent/(temp_input_dem.stem + '_slope' + temp_input_dem.suffix)
                slope_from_dem(temp_input_dem, temp_output_slope_map, scale)
                
                # Reproject to s_srs
                # Construct command prompt
                cmd = "gdalwarp -t_srs " + s_srs + \
                    " -of GTiff -r near -nosrcalpha -wo SOURCE_EXTRA=1000 -dstnodata -9999 " \
                    + '-ts ' + str(width) + ' ' + str(height) + ' ' \
                    +  str(temp_output_slope_map) + " " + str(output_slope_map)
                
                
                print('Reprojecting with gdalwarp\n')
                print(cmd)
                print('')
                
                # Execute the command in console
                p = subprocess.Popen(cmd, shell=True, cwd=str(dempath) ,stderr=subprocess.PIPE)
                # Wait until process is finished
                (output, err) = p.communicate()
                p_status = p.wait() # This makes the wait possible
                print(err) # Print any error to screen
                
                # Delete temp file
                temp_output_slope_map.unlink()
                
                
                
            else:
                # Run on original input dem
                slope_from_dem(input_dem, output_slope_map, scale)
            
            
            # Add the new file to raster sheet of the config file
            dfrasters = self.list_raster_layers()
            dfcomp = self.list_computed_layers()
            
            filename = output_slope_map.name
            
            # Add new file to config file
            if filename not in list(dfcomp.filename):
                startrow = len(dfcomp) + 1 # (add row for header and one for new row)
                filepath = output_slope_map.parent
                filepath = Path('../Data/'+str(filepath).split('Data')[1])
                source = 'Computed from ' + input_dem.name 
                row_dict = {'id':np.nan,
                            'layer_name': output_slope_map.stem, 
                            'layer_type':'DEM slope',
                            'filename': output_slope_map.name,
                            'filepath': str(filepath.as_posix()),
                            'source': source,
                            'reference':'',
                            }
                df = pd.DataFrame([row_dict])
                # Append row to excel
                if self.configfile.suffix == '.xlsx':
                    append_df_to_excel(str(self.configfile), df, sheet_name='Computed', 
                                        header=None, startrow=startrow, index=False)
                elif self.configfile.suffix == '.json':
                    
                    # Read json file
                    with open(str(self.configfile), 'r') as file:
                        raw_content = file.read()
                        data = json.loads(raw_content)
                    
                    data['Computed'].append( row_dict )
                    # Write data to file
                    with open(str(self.configfile), 'w') as f:
                        json.dump(data, f, indent=4)
                    

        # Aspect
        if 'aspect' in methods:
            pass
        
        # Color-relief
        if 'color-relief' in methods:
            # TODO
            pass
            
        # Terrain Ruggedness Index TRI
        if 'TRI' in methods:
            pass
        
        # Topographic Position Index TPI
        if 'TPI' in methods:
            # TODO
            pass
        
        # Roughness
        if 'roughness' in methods:
            # Get fullfilename of output dem
            output_roughness_map = input_dem.parent/(input_dem.stem + '_roughness' + input_dem.suffix)
            
            # Call wrapper function from gis_tools.py
            from planetary.gis_tools import roughness_from_dem
            if 'proj=longlat' in proj4_str:
                # Run on re-projected dem
                temp_output_roughness_map = temp_input_dem.parent/(temp_input_dem.stem + '_roughness' + temp_input_dem.suffix)
                roughness_from_dem(temp_input_dem, temp_output_roughness_map)
                
                # Reproject to s_srs
                # Construct command prompt
                cmd = "gdalwarp -t_srs " + s_srs + \
                    " -of GTiff -r near -nosrcalpha -wo SOURCE_EXTRA=1000 -dstnodata -9999 " \
                    + '-ts ' + str(width) + ' ' + str(height) + ' ' \
                    +  str(temp_output_roughness_map) + " " + str(output_roughness_map)
                
                
                print('Reprojecting with gdalwarp\n')
                print(cmd)
                print('')
                
                # Execute the command in console
                p = subprocess.Popen(cmd, shell=True, cwd=str(dempath) ,stderr=subprocess.PIPE)
                # Wait until process is finished
                (output, err) = p.communicate()
                p_status = p.wait() # This makes the wait possible
                print(err) # Print any error to screen
                
                # Delete temp file
                temp_output_roughness_map.unlink()
            
            else:
                # Use original dem
                roughness_from_dem(input_dem, output_roughness_map)
            
            # Add the new file to raster sheet of the config file
            # Add the new file to raster sheet of the config file
            
            dfrasters = self.list_raster_layers()
            dfcomp = self.list_computed_layers()
            
            filename = output_roughness_map.name
            
            # Add new file to config file
            if filename not in list(dfcomp.filename):
                startrow = len(dfcomp) + 1 # (add row for header and one for new row)
                filepath = output_roughness_map.parent
                filepath = Path('../Data/'+str(filepath).split('Data')[1])
                source = 'Computed from ' + input_dem.name 
                row_dict = {'id':np.nan,
                            'layer_name': output_roughness_map.stem, 
                            'layer_type':'DEM roughness',
                            'filename': output_roughness_map.name,
                            'filepath': str(filepath.as_posix()),
                            'source': source,
                            'reference':'',
                            }
                df = pd.DataFrame([row_dict])
                if self.configfile.suffix == '.xlsx':
                    append_df_to_excel(str(self.configfile), df, sheet_name='Computed', 
                                        header=None, startrow=startrow, index=False)
                elif self.configfile.suffix == '.json':
                    # Read json file
                    with open(str(self.configfile), 'r') as file:
                        raw_content = file.read()
                        data = json.loads(raw_content)
                    
                    data['Computed'].append( row_dict )
                    # Write data to file
                    with open(str(self.configfile), 'w') as f:
                        json.dump(data, f, indent=4)
        
        # Update list of raster and layers
        dfLayers = self.list_all_layers()
        self.layers = list(dfLayers.layer_name)
        self.rasters = list(dfLayers.filename)
        
        
        # Clean up temp files
        if 'proj=longlat' in proj4_str:
            if temp_input_dem.exists():
                temp_input_dem.unlink() # Delete file if it exists
        
        
        
        return    
    
    def rasterize_shapefile(self, shape_file, dst_file, match_raster_file):
        # Generate a raster of the south pole psrs from a shapefile.
        # Output raster extent and resolution matching that of a defined raster.
        
        # Get input shapefile
        # Check if file is found
        if shape_file not in self.shapes:
            raise ValueError('{} shapefile not found.'.format(shape_file))
        # Load list of all layers
        dfShapes = self.list_shapefile_layers()
        # Get the filepath
        shapepath = dfShapes['filepath'][dfShapes.filename == shape_file].iloc[0]
        # Get fullfilename of input dem
        shape_file = shapepath/shape_file
        
        # Get full name of matching raster file
        # Check if file is found
        if match_raster_file not in self.rasters + self.layers:
            raise ValueError('{} raster not found.'.format(match_raster_file))
        # Load list of all layers
        dfLayers = self.list_all_layers()
        # Get the filepath
        rasterpath = dfLayers['filepath'][dfLayers.filename == match_raster_file].iloc[0]
        # Get fullfilename of input dem
        match_raster_file = rasterpath/match_raster_file
        
        
        # Set output filename
        dst_file = self.data_dir/dst_file

        
        # TODO: Wrapper function to gis_tools function
        from planetary.gis_tools import rasterize_layer_match_raster
        rasterize_layer_match_raster(shape_file, dst_file, match_raster_file)
        
        
        # Add layer to config
        dfrasters = self.list_raster_layers()
        dfcomp = self.list_computed_layers()
        
        filename = dst_file.name
        
        # Add new file to config file
        if filename not in list(dfcomp.filename):
            startrow = len(dfcomp) + 1 # (add row for header and one for new row)
            filepath = dst_file.parent
            filepath = Path('../Data/'+str(filepath).split('Data')[1])
            source = 'Computed from ' + shape_file.name 
            row_dict = {'id':np.nan,
                        'layer_name': dst_file.stem, 
                        'layer_type':'Rasterized Shp',
                        'filename': dst_file.name,
                        'filepath': filepath,
                        'source': source,
                        'reference':'',
                        }
            df = pd.DataFrame([row_dict])
            if self.configfile.suffix == '.xlsx':
                append_df_to_excel(str(self.configfile), df, sheet_name='Computed', 
                                    header=None, startrow=startrow, index=False)
            elif self.configfile.suffix == '.json':
                
                # Read json file
                with open(str(self.configfile), 'r') as file:
                    raw_content = file.read()
                    data = json.loads(raw_content)
                
                data['Computed'].append( {'layer_name': dst_file.stem, 
                                            'layer_type':'Rasterized Shp',
                                            'filename': dst_file.name,
                                            'filepath': str(filepath.as_posix()),
                                            'source': source,
                                            'reference':'',
                                            } )
                # Write data to file
                with open(str(self.configfile), 'w') as f:
                    json.dump(data, f, indent=4)
            
            
    
        # Update list of raster and layers
        dfLayers = self.list_all_layers()
        self.layers = list(dfLayers.layer_name)
        self.rasters = list(dfLayers.filename)
        
        
        return
    
    def generate_crater_density_raster():
        
        # TODO: Create a map of crater density
        # Use database of known craters.
        # Possibly expand with crater detection from raster image using pyCDA
        #
        # Perform a kernel desnsity estimation to get a map of crater density
        
        # See: https://github.com/openplanetary/vespamap19tutorials/blob/master/planetaryskl/notebooks/datadiscovery.ipynb
        
        
        return
    
    
    # Generate Custom Constrait Maps ------------------------------------------
    # Methods to create raster maps of regions meeting constraints
    # 
    
    # 
    # Output: raster with integer values of different regions.
    # Option to convert to vector shapefile.
    
    def generate_constraint_map(self,dem_file = None, elev_const = [None,None],       # DEM elevation
                                slope_file = None, slope_const = [None,None],         # DEM Slope 
                                aspect_file = None, aspect_const = [None,None],       # DEM Aspect
                                roughness_file = None, roughness_const = [None,None], # DEM Roughness
                                prox_psr_file = None, prox_psr_const = [None,None],   # Proximity to psr
                                out_file = 'custom_constraints.tif', # Output filename
                                out_path = None,
                                out_type = 'raster', # Output file type (Raster or Vector)
                                output='rgb', # Output type (binary or rgb) single of 3-band raster
                                ):
        '''
        Apply constraints to a set of raster files and return a new raster file
        of areas meeting those contstraints.
        
        Constraint options include
        
        elevation = [min, max]
        aspect = [min, max]
        slope = [min, max]
        roughness = [min, max]
        proximity_to_psr = [min, max]
        (other proximity maps)
        viewshed ? from ceratin point
        
        Example:
        Generate a custom constraint map for areas with slope < 20 degrees and
        proximity to psr < 10,000 m:
        >> LunaSthPole.generate_constraint_map(slope_file=slope_file,slope_const=[0.,20.],prox_psr_file=prox_psr_file,prox_psr_const=[0.,10000.])
        >> LunaSthPole.plot_raster_cartopy('custom_constraints.tif')
        
        '''
        
        # 1. Get file sizes and determine if need to re-sample
        
        # Get list of files supplied
        files = [dem_file,slope_file,aspect_file,roughness_file,prox_psr_file]
        # Get list of raster sizes
        sizes = [None,None,None,None,None]
        for i, file in enumerate(files):
            if file is not None:
                sizes[i] = self.get_raster_size(file)
        
        # Get output size (first non-null value)
        ind = next(i for i, j in enumerate(sizes) if j)
        out_size = sizes[ind]
        out_file_init = files[ind] # File to initialize outfile from
        
        # TODO: alternative methods (largest, smallest, median, etc.)
        
        # 2. Apply constraints ------------------------------------------------
        
        # Instantiate output data
        data = None
        
        # DEM elevation 
        if dem_file is not None:
            elev = self.get_raster_array(dem_file)
            elev_size = self.get_raster_size(dem_file)
            if elev_const[0] is not None:
                elev[elev < elev_const[0]] = np.nan
            if elev_const[1] is not None:
                elev[elev > elev_const[1]] = np.nan
            # Create elevation mask [1/0]
            elev_mask = elev.copy()
            elev_mask[~np.isnan(elev_mask)] = 1
            elev_mask[np.isnan(elev_mask)] = 0
            # Add to data
            if data is None:
                data = elev_mask.copy()
            else:
                # data += elev_mask
                data = np.logical_and(data, elev_mask).astype(int)
            del elev, elev_mask
            
        # DEM slope
        if slope_file is not None:
            slope = self.get_raster_array(slope_file)
            slope_size = self.get_raster_size(slope_file)
            if slope_const[0] is not None:
                slope[slope < slope_const[0]] = np.nan
            if slope_const[1] is not None:
                slope[slope > slope_const[1]] = np.nan
            # Create elevation mask [1/0]
            slope_mask = slope.copy()
            slope_mask[~np.isnan(slope_mask)] = 1
            slope_mask[np.isnan(slope_mask)] = 0
            # Add to data
            if data is None:
                data = slope_mask.copy()
            else:
                # data += slope_mask
                data = np.logical_and(data, slope_mask).astype(int)
            del slope, slope_mask
            
        # DEM aspect
        if aspect_file is not None:
            aspect = self.get_raster_array(aspect_file)
            aspect_size = self.get_raster_size(aspect_file)
            if aspect_const[0] is not None:
                aspect[aspect < aspect_const[0]] = np.nan
            if aspect_const[1] is not None:
                aspect[aspect > aspect_const[1]] = np.nan
            # Create elevation mask [1/0]
            aspect_mask = aspect.copy()
            aspect_mask[~np.isnan(aspect_mask)] = 1
            aspect_mask[np.isnan(aspect_mask)] = 0
            # Add to data
            if data is None:
                data = aspect_mask.copy()
            else:
                # data += aspect_mask
                data = np.logical_and(data, aspect_mask).astype(int)
            del aspect, aspect_mask 
        
        # DEM roughness
        if roughness_file is not None:
            roughness = self.get_raster_array(roughness_file)
            roughness_size = self.get_raster_size(roughness_file)
            if roughness_const[0] is not None:
                roughness[roughness < roughness_const[0]] = np.nan
            if roughness_const[1] is not None:
                roughness[roughness > roughness_const[1]] = np.nan
            # Create elevation mask [1/0]
            roughness_mask = roughness.copy()
            roughness_mask[~np.isnan(roughness_mask)] = 1
            roughness_mask[np.isnan(roughness_mask)] = 0
            # Add to data
            if data is None:
                data = roughness_mask.copy()
            else:
                # data += roughness_mask
                data = np.logical_and(data, roughness_mask).astype(int)
            del roughness, roughness_mask 
        
        # Proximity
        if prox_psr_file is not None:
            prox_psr = self.get_raster_array(prox_psr_file)
            prox_psr_size = self.get_raster_size(prox_psr_file)
            if prox_psr_const[0] is not None:
                prox_psr[prox_psr < prox_psr_const[0]] = np.nan
            if prox_psr_const[1] is not None:
                prox_psr[prox_psr > prox_psr_const[1]] = np.nan
            # Create elevation mask [1/0]
            prox_psr_mask = prox_psr.copy()
            prox_psr_mask[~np.isnan(prox_psr_mask)] = 1
            prox_psr_mask[np.isnan(prox_psr_mask)] = 0
            # Add to data
            if data is None:
                data = prox_psr_mask.copy()
            else:
                # data += prox_psr_mask
                data = np.logical_and(data, prox_psr_mask)
            del prox_psr, prox_psr_mask 
            
        # Restrict to binary
        data[data>0] = 1
        
        
        
        # 3. Create output rast------------------------------------------------
        
        # Initialize the output file to match one of the selected input files
        # (selected above as out_file_init)
            
        if out_path is None:
            out_path = self.data_dir
        out_file_full = str(out_path/out_file) # Full filename of output

        
        in_ds = self.get_raster_ds(out_file_init)
        
        if output in ['binary']:
            # Create file (single-band raster)
            data = (data* 255).astype(np.uint8) # Scale to 0-255
            driver = gdal.GetDriverByName('GTiff')
            out_ds = driver.Create(out_file_full, in_ds.RasterXSize, in_ds.RasterYSize, 1, gdal.GDT_Byte)
            # Set projection and geotransform from in_file
            out_ds.SetProjection(in_ds.GetProjection())
            out_ds.SetGeoTransform(in_ds.GetGeoTransform())
            # Initialize data
            out_band = out_ds.GetRasterBand(1)
            out_band.WriteArray(data)
            out_band.FlushCache()
            out_band.ComputeStatistics(False)
        
        elif output=='rgb':
            # Cretae RGB raster file
            # 1. Scale binary (0,1) to 8-bit bytes (0,255)
            # 0 = Black, 255 = White
            rgb_data = (data * 255).astype(np.uint8)
            # Setup driver
            driver = gdal.GetDriverByName('GTiff')
            out_ds = driver.Create(out_file_full, in_ds.RasterXSize, in_ds.RasterYSize, 3, gdal.GDT_Byte)
            # Set projection and geotransform from in_file
            out_ds.SetProjection(in_ds.GetProjection())
            out_ds.SetGeoTransform(in_ds.GetGeoTransform())
            # Initialize data
            for i, color_int in enumerate([gdal.GCI_RedBand, gdal.GCI_GreenBand, gdal.GCI_BlueBand], 1):
                out_band = out_ds.GetRasterBand(i)
                out_band.WriteArray(rgb_data)
                out_band.SetColorInterpretation(color_int)
            out_ds.FlushCache() 
        
        
        # Add description to the metadata
        desc = 'Custom binary constraint map. '
        if dem_file is not None:
            desc = desc + 'Elevation (m): ' + str(elev_const) + " & "
        if slope_file is not None:
            desc = desc + 'Slope (deg): ' + str(slope_const) + " & "
        if aspect_file is not None:
            desc = desc + 'Aspect (deg): ' + str(aspect_const) + " & "
        if roughness_file is not None:
            desc = desc + 'Roughness: ' + str(roughness_const) + " & "
        if prox_psr_file is not None:
            desc = desc + 'PSR proximity (m): ' + str(prox_psr_const) + " & "
        
        desc = desc[:-3]
        
        out_band.SetDescription(desc)
        
        out_ds = None # Close file
        
        # 4. Add new file to config file --------------------------------------
        
        dfrasters = self.list_raster_layers()
        dfcomp = self.list_computed_layers()
        
        if out_file not in list(dfcomp.filename):
            startrow = len(dfcomp) + 1 # (add row for header and one for new row)
            filepath = Path('../Data/'+str(out_path).split('Data')[1])
            # source = 'Computed from: ' + files[files is not None]
            source = 'Computed from ' + dem_file
            row_dict = {'id':np.nan,
                        'layer_name': out_file, 
                        'layer_type':'Binary constraint map',
                        'filename': out_file,
                        'filepath': str(filepath.as_posix()),
                        'source': source,
                        'reference':'',
                        }
            df = pd.DataFrame([row_dict])
            # append_df_to_excel(str(self.configfile), df, sheet_name='Computed', 
            #                     header=None, startrow=startrow, index=False)
            
            if self.configfile.suffix == '.xlsx':
                append_df_to_excel(str(self.configfile), df, sheet_name='Computed', 
                                    header=None, startrow=startrow, index=False)
            elif self.configfile.suffix == '.json':
                
                # Read json file
                with open(str(self.configfile), 'r') as file:
                    raw_content = file.read()
                    data = json.loads(raw_content)
                
                data['Computed'].append( row_dict )
                # Write data to file
                with open(str(self.configfile), 'w') as f:
                    json.dump(data, f, indent=4)
            
            
            
        
        # Update list of raster and layers
        dfLayers = self.list_all_layers()
        self.layers = list(dfLayers.layer_name)
        self.rasters = list(dfLayers.filename)
        
        # pdb.set_trace()
        # vals = self.get_raster_array(out_file)
        
        return
    
    
    # Add Child objects -------------------------------------------------------
    def add_craters(self):
        '''
        Add a list of craters.

        Returns
        -------
        None.

        '''
        
        # Get list of craters
        self.craters = self.list_craters()
        
        return
    
    def SetPlanetaryTerrain(self, demfile, meshtype='pyvista',mesh_frame='raster',units='m'):
        
        # Generate a PlanetaryTerrain object.
        
        
        # Check if file is found
        if demfile not in self.rasters + self.layers:
            raise ValueError('{} dem raster not found.'.format(demfile))
        
        
        # Load list of all layers
        dfLayers = self.list_all_layers()
        
        # Get the filepath
        dempath = dfLayers['filepath'][dfLayers.filename == demfile].iloc[0]
        
        # Generate PlanetaryTerrain object
        terrain = PlanetaryTerrain.from_dem(dempath,demfile,planet=self.planet,
                                            meshtype=meshtype,mesh_frame=mesh_frame,units=units) 
        
        # Append to self
        self.terrain = terrain
        
        return
    
    # Getter functions --------------------------------------------------------
    # Get details of a raster file by name
    
    def get_raster_filepath(self,raster_name):
        '''
        Get the path name of a raster file included in the region.

        Parameters
        ----------
        raster_name : TYPE
            DESCRIPTION.

        Returns
        -------
        filepath : Pathlib path
            Absolute filepath of the file.

        '''
        
        if raster_name not in self.rasters + self.layers:
            raise ValueError('{} raster not found.'.format(raster_name))
        
        # Load list of all layers
        dfLayers = self.list_all_layers()
        # Get the filepath
        filepath = dfLayers['filepath'][dfLayers.filename == raster_name].iloc[0]
        
        return filepath
    
    def get_raster_filename(self,raster_name):
        '''
        Get the full filename name of a raster file included in the region.

        Parameters
        ----------
        raster_name : TYPE
            DESCRIPTION.

        Returns
        -------
        filepath : Pathlib path
            Absolute filepath of the file.

        '''
        
        if raster_name not in self.rasters + self.layers:
            raise ValueError('{} raster not found.'.format(raster_name))
        
        # Load list of all layers
        dfLayers = self.list_all_layers()
        # Get the filepath
        filepath = dfLayers['filepath'][dfLayers.filename == raster_name].iloc[0]
        filename = dfLayers['filename'][dfLayers.filename == raster_name].iloc[0]
        
        fullfilename = filepath/filename
        
        return fullfilename
    
    def get_raster_size(self,raster_name):
        '''
        Get the pixel size of a raster file included in the region.

        Parameters
        ----------
        raster_name : TYPE
            DESCRIPTION.

        Returns
        -------
        size : tuple
            Pixel size (X,Y)

        '''
        
        if raster_name not in self.rasters + self.layers:
            raise ValueError('{} raster not found.'.format(raster_name))
        
        # Load list of all layers
        dfLayers = self.list_all_layers()
        
        # Get raster pixel size
        size = dfLayers['pixel_size'][dfLayers.filename == raster_name].iloc[0]
        # Convert to tuple
        if type(size) == str:
            size = tuple(int(x) for x in size.strip('()').split(','))
        
        return size
    
    
    def get_raster_ds(self,raster_name):
        '''
        Get the gdal dataset of a raster file.
        Contains information on the image data, crs, geotransform.

        Warning! Close raster file after use by setting ds = None

        Parameters
        ----------
        raster_name : TYPE
            DESCRIPTION.

        Returns
        -------
        ds : osgeo.gdal.Dataset
            Raster dataset.

        '''
        
        
        # Load list of WMS rasters
        dfWMS = self.list_wms_layers()
        # Load list of all layers
        dfLayers = self.list_all_layers()
        
        if raster_name not in self.rasters + self.layers:
            raise ValueError('{} raster not found.'.format(raster_name))
        
        
        # Get Filename.
        # Check if raster_name is in dfWMS and get filename
        if raster_name in list(dfWMS.filename):
            # raster_name is the name of the tif file
            
            # Get filename
            filename = dfWMS['filename'][dfWMS.filename == raster_name].iloc[0]
            filepath = dfWMS['filepath'][dfWMS.filename == raster_name].iloc[0]
            # Get target srs
            t_srs = dfWMS['t_srs'][dfWMS.filename == raster_name].iloc[0]
            
            
            
        elif raster_name in list(dfWMS.layer_name):
            # raster_name is the name of the wms layer
            
            # Get filename
            filename = dfWMS['filename'][dfWMS.layer_name == raster_name].iloc[0]
            filepath = dfWMS['filepath'][dfWMS.layer_name == raster_name].iloc[0]
            # Get target srs
            t_srs = dfWMS['t_srs'][dfWMS.layer_name == raster_name].iloc[0]
        
        elif raster_name in list(dfLayers.layer_name):
            
            # Get filename
            filename = dfLayers['filename'][dfLayers.layer_name == raster_name].iloc[0]
        elif raster_name in list(dfLayers.filename):
            
            # Get filename
            filename = dfLayers['filename'][dfLayers.filename == raster_name].iloc[0]    
            filepath = dfLayers['filepath'][dfLayers.filename == raster_name].iloc[0]    
        
            
        else:
            # TODO: add case where filename is not from wms
            raise ValueError('{} raster not found.'.format(raster_name))
        
        # Get Fullfilename
        fullfilename = filepath/ filename
        
        
        # Read data from raster
        
        # Open the image using gdal
        ds = gdal.Open(str(fullfilename))
        
        return ds
    
    def get_raster_gt(self, raster_name):
        '''
        Return the raster's geotransform.
        gt = [originX, pixelWidth, 0, originY, 0, pixelHeight]

        Parameters
        ----------
        raster_name : TYPE
            DESCRIPTION.

        Returns
        -------
        gt : TYPE
            DESCRIPTION.

        '''
        
        # Get the image data as an array
        
        # Get the fullfilename
        fullfilename = self.get_raster_filename(raster_name)

        # 1. Read data from raster --------------------------------------------
        # Open the image using gdal
        ds = gdal.Open(str(fullfilename))
        
        # Projection in WKT
        proj_wkt = ds.GetProjection()
        # e.g. 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST],AUTHORITY["EPSG","4326"]]'
        # Note: WGS84 = EPSG4326 = PlateCarree
        
        # Convert projection to osr SpatialReference object
        inproj = osr.SpatialReference()
        inproj.ImportFromWkt(proj_wkt)
        
        # Proj4 string
        inproj_proj4 = inproj.ExportToProj4() 
        
        # Geotransform
        gt = ds.GetGeoTransform()
        
        
        
        return gt
    
    def get_raster_proj4(self, raster_name):
        '''
        Return the raster's proj4 string.

        Parameters
        ----------
        raster_name : TYPE
            DESCRIPTION.

        Returns
        -------
        gt : TYPE
            DESCRIPTION.

        '''
        
        # Get the image data as an array
        
        # Get the fullfilename
        fullfilename = self.get_raster_filename(raster_name)

        # 1. Read data from raster --------------------------------------------
        # Open the image using gdal
        ds = gdal.Open(str(fullfilename))
        
        # Projection in WKT
        proj_wkt = ds.GetProjection()
        # e.g. 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST],AUTHORITY["EPSG","4326"]]'
        # Note: WGS84 = EPSG4326 = PlateCarree
        
        # Convert projection to osr SpatialReference object
        inproj = osr.SpatialReference()
        inproj.ImportFromWkt(proj_wkt)
        
        # Proj4 string
        inproj_proj4 = inproj.ExportToProj4() 
        
        # Geotransform
        gt = ds.GetGeoTransform()
        
        return inproj_proj4
    
    def get_raster_array(self, raster_name):
        
        # Get the image data as an array
        
        # Get the fullfilename
        fullfilename = self.get_raster_filename(raster_name)

        # 1. Read data from raster --------------------------------------------
        # Open the image using gdal
        ds = gdal.Open(str(fullfilename))
        
        
        # Extract the image data
        # Note: Cartopy/matplotlib requires the color bands to be in the last 
        # dimension of an array (i.e., row, col, band), wheras gdal data is in 
        # (band,row,col)? So we use np.transpose(im, [1,2,0]) to reorder the 
        # dimensions.
        
         # Image data as array of pixels
        img_data = ds.ReadAsArray()
        
        if len(img_data.shape) == 2:
            # Single band
            img = img_data # 2D image array
            # cmap = 'jet'        # Color map
        else:
            # Multiband data.
            img = img_data[:3, :, :].transpose((1, 2, 0)) # Reorder dimensions
            cmap = None # Use rgb values for color
            if img.shape[2] < 3:
                # Image only has 2 bands
                # Plot single band image as colormap
                cmap = 'gray'
                img = img[:,:,0] # Select first band only
                # img = newimg
        
        # Get nodata value of raster band (-9999.)
        nodataval = ds.GetRasterBand(1).GetNoDataValue() # Get nodata value from first band       
        # Replace nodataval with nan
        if (nodataval is not None) & (nodataval != 0.):
            try:
                img[img == nodataval] = np.nan
            except:
                # Integer values.
                if nodataval in img:
                    img[img == nodataval] = np.nan
        
        ds = None # Close file
        
        return img
    
    def get_raster_pixel_coords(self,raster_name):
        
        # Get an array of x and y pixel coordinates
        
        # Get the fullfilename
        fullfilename = self.get_raster_filename(raster_name)
        
        # Open the image using gdal
        ds = gdal.Open(str(fullfilename))
        
        # Projection in WKT
        proj_wkt = ds.GetProjection()
        # e.g. 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST],AUTHORITY["EPSG","4326"]]'
        # Note: WGS84 = EPSG4326 = PlateCarree
        
        # Convert projection to osr SpatialReference object
        inproj = osr.SpatialReference()
        inproj.ImportFromWkt(proj_wkt)
        
        # Proj4 string
        inproj_proj4 = inproj.ExportToProj4() 
        
        # Geotransform
        gt = ds.GetGeoTransform()
        
        # Get image extent from transform (in srs)
        img_extent = (gt[0], gt[0] + ds.RasterXSize * gt[1],
                      gt[3] + ds.RasterYSize * gt[5], gt[3])
        
        # Extract x/y limits of image
        minx = img_extent[0] # gt[0]
        maxx = img_extent[1]  # minx + ds.RasterXSize *gt[1]
        miny = img_extent[2]  # gt[3] + ysize *gt[5]
        maxy = gt[3]
        
        # Create mesh -------------------------------------------------------------
        
        # Create coords in srs
        x = np.arange(minx,maxx,gt[1]) # Array of x values
        y = np.arange(maxy,miny,gt[5]) # Array of y values
        
        # Create mesh
        X, Y = np.meshgrid(x,y) 

        return X, Y
    
    def get_wms_connections(self):
        
        # Make a connection to the wms and return the wms object
        
        # Get list of WMS layers
        dfWMS = self.list_wms_layers()
        
        # Instantiate wms dictionary
        wms_dict = pd.DataFrame(columns=['wms_name','wms'])
        
        # Loop through files and check if file has been created
        for i, row in dfWMS.iterrows():
            
            # Get existance status fo tif file
            exists = row.exists

            # Extract details of layer
            wms_name = row.wms_name
            wms_url = row.wms_url
            wms_version = row.wms_version
            
            # Create wms connection
            if (len(wms_dict)>0) & (wms_name in list(wms_dict['wms_name'])):
                # WMS connection already made - extract from dataframe
                wms = wms_dict['wms'][wms_dict.wms_name == wms_name].iloc[0]
            else:
                # Create new wms connection
                print('\nConnecting to WMS: {}\n'.format(wms_url))
                wms = WebMapService(url=wms_url, version=wms_version)
                # Append wms connection to wms_dict
                # wms_dict['wms_name'] = wms_name
                # wms_dict['wms'] = wms
                wms_dict = wms_dict.append({'wms_name':wms_name,'wms':wms} , ignore_index=True)
            
        
        return wms_dict
    
    
    # Shapefile getters -------------------------------------------------------
    
    def get_shapes(self,shapefile, match_proj=None ,restrict=False):
        
        # Check the shapefile is included in config
        if shapefile not in self.shapes:
            raise ValueError('{} shapefile not found.'.format(shapefile))
        
        # Get full filename of the shapefile
        # Load list of all layers
        dfShapes = self.list_shapefile_layers()
        # Get the filepath
        shapepath = dfShapes['filepath'][dfShapes.filename == shapefile].iloc[0]
        # Get fullfilename of input dem
        shapefile = shapepath/shapefile
        
        # Load the dbf file
        dbf_file = shapepath/(shapefile.stem+'.dbf')
        if dbf_file.exists():
            # Load the data into a geopandas dataframe
            # df = gpd.read_file(dbf_file)
            df = gpd.read_file(shapefile)
        else:
            df = gpd.read_file(shapefile)
        
        # Reproject to match an output
        if match_proj is not None:
            # Get projection of raster
            match_proj4 = self.get_raster_proj4(match_proj)
            # Reproject dataframe
            df = df.to_crs(match_proj4)
        
        # Get the proj4 string
        proj4_str = df.crs.to_proj4()
        
        # Restrict the dataset by the region
        if restrict == True:
            
            # Get the bounding box of the region
            bbox_df = gpd.GeoDataFrame(gpd.GeoSeries(self.bbox_geom), columns=['geometry'])
            # bbox_df.crs = {'init' :'epsg:4326'}
            bbox_df.crs = self.longlat_proj4
            
                           
            # Reproject to match df srs
            bbox_df = bbox_df.to_crs(proj4_str)
            
            # Fix up region by taking envelope
            # Get the polygon
            bbox_poly = bbox_df['geometry'].iloc[0]
            # Create new polygon with boundary of the previous one
            bbox_poly1 = shapely.geometry.box(*bbox_poly.bounds)
            
            # Convert back to a dataframe
            bbox_df = gpd.GeoDataFrame(gpd.GeoSeries(bbox_poly1), columns=['geometry'])
            bbox_df.crs = proj4_str
            
            # Find subset of shapes in bbox
            df = gpd.overlay(df, bbox_df, how='intersection')
        
        return df
    
    
    # Plotting methods --------------------------------------------------------
    
    def plot_shape_cartopy(self, shape_name, showgrid=True, alpha=1.):
        
        # Load list of shape files
        dfShapes = self.list_shapefile_layers()
        
        # Check if shape_name is in dfShapes and get filename
        if shape_name in list(dfShapes.filename):
            # raster_name is the name of the tif file
            
            # Get filename and filepath
            filename = dfShapes['filename'][dfShapes.filename == shape_name].iloc[0]
            filepath = dfShapes['filepath'][dfShapes.filename == shape_name].iloc[0]
        
        # Get Fullfilename
        fullfilename = filepath / filename
        
        t_srs = "EPSG:4326"
        
        
        # Read shapefile data from .dbf
        gdf = self.get_shapes(shape_name, match_proj=self.rasters[0])
        
        # 2. Set the extent (minx, maxx, miny, maxy)
        # Example: Focusing on a specific region
        extent = [self.long_min, self.long_max, self.lat_min, self.lat_max] 
        # Filter geometries using spatial indexer .cx
        gdf_sub = gdf.cx[extent[0]:extent[1], extent[2]:extent[3]]
        
        
        
        # 2. Set up cartopy parameters ----------------------------------------
        
        # Specify cartopy ellipsoid
        if self.planet in ['Luna','luna']:
            ellipsoid = ccrs.Globe(semimajor_axis=1737400, semiminor_axis=1737400,ellipse=None)
        if self.planet in ['Mars','mars']:
            ellipsoid = ccrs.Globe(semimajor_axis=3396190, semiminor_axis=3376200,ellipse=None)

        # TODO: Add ellipsoids of other planets
        
        # Specify cartopy crs projection
        if t_srs in ['EPSG:4326']:
            # EPSG:4326 == PlateCarree
            data_crs = ccrs.PlateCarree(globe=ellipsoid)     
        elif t_srs in ['IAU2000:30120','South Pole','South']:
            data_crs = ccrs.SouthPolarStereo(globe=ellipsoid)
            # Alternative: if 'stereo' in proj4_string
        elif t_srs == 'from_shp':
            # Get the crs from the shp
            pass
        
        
        # Create a new axes ---------------------------------------------------
        
        fig = plt.figure() # figsize=(10, 5)
        ax = fig.add_subplot(1, 1, 1, projection=data_crs)
        plt.title(filename)
        
        # # Add the image
        # im = ax.imshow(img, origin='upper', extent=img_extent,alpha=alpha,
        #                 interpolation='nearest',
        #                 cmap=cmap,
        #                 transform=data_crs) # transform=crs of input data
        
        
        
        # Create a colormap for shapes
        # Use: https://imagecolorpicker.com/
        import matplotlib.cm as cm
        cmap = cm.get_cmap('viridis', len(gdf_sub))
        color_dict = {'Ccc':'#fadc02',
                      'Csc':'#ffffbe',
                      'Ec': '#a5ce30',
                      'Ecc': '#6ec400',
                      'Esc':'#6ec400',
                      'Em': '#f10d0c',
                      'EIp':'#e54d74',
                      'Ic': '#6b20df',
                      'Ic1':'#2116f8',
                      'Ic2':'#1c7cf7',
                      'Icc':'#97dbf2',
                      'Isc':'#004da7',
                      'Icf':'#f28bb8',
                      'Ib':'#44648a',
                      'Ibm':'#bc424d',
                      'Id':'#ff3600',
                      'Ig':'#73b2c3',
                      'Iia':'#2a5ed4',
                      'Iiap': '#6f4489',
                      'Iic':'#1091ca',
                      'Iif':'#aa58e0',
                      'Im1':'#e400c5',
                      'Im2':'#fe3362',
                      'Imd':'#fc029a',
                      'Iohi':'#a6d5ff',
                      'Ioho':'#c4e8ff',
                      'Ios':'#00abb3',
                      'Iom':'#7795db',
                      'Iork':'#52b9fc',
                      'Iorm':'#465fb9',
                      'Ip':'#caa4cd',
                      'It':'#cda7f0',
                      'Itd':'#02aff1',
                      'INp':'#73b2c3',
                      'INt':'#cbacaa',
                      'Nc':'#c96936',
                      'Nb':'#f4c784',
                      'Nbl':'#ffcdba',
                      'Nbm':'#ffccbe',
                      'Nbsc':'#f3a263',
                      'Nnj':'#ffffbe',
                      'Np':'#f0bcae',
                      'Nt':'#fbd5d4',
                      'Ntp':'#efbfcf',
                      'pNb':'#64442f',
                      'pNbm':'#64442f',
                      'pNc':'#7b3e29',
                      'pNt':'#dd9f92'
                      }
        
        # Iterate and plot with different colors
        for i, (index, row) in enumerate(gdf_sub.iterrows()):
            unit = row['FIRST_Unit'] # Get unit
            ax.add_geometries([row['geometry']], crs=ccrs.PlateCarree(globe=ellipsoid),
                              facecolor=color_dict[unit], edgecolor='black', alpha=0.7)
            pdb.set_trace()
        
       
        # 3. Add to map and zoom
        # Extent: [West, East, South, North]
        ax.set_extent([self.long_min, self.long_max, self.lat_min, self.lat_max], crs=ccrs.PlateCarree(globe=ellipsoid))
        plt.show()
        
        return
    
    
    def plot_raster_cartopy(self,raster_name, shape_name=None, cmap='jet', showgrid=True, alpha=1., alpha_shp=0.5):
        
        # Load list of WMS rasters
        dfWMS = self.list_wms_layers()
        dfRasters = self.list_raster_layers()
        dfLayers = self.list_all_layers()
        
        
        # Get Filename and filepath
        # TODO: Replace this code block with the self.get_raster_filename method
        
        # Check if raster_name is in dfWMS and get filename
        if raster_name in list(dfWMS.filename):
            # raster_name is the name of the tif file
            
            # Get filename and filepath
            filename = dfWMS['filename'][dfWMS.filename == raster_name].iloc[0]
            filepath = dfWMS['filepath'][dfWMS.filename == raster_name].iloc[0]
            # Get target srs
            t_srs = dfWMS['t_srs'][dfWMS.filename == raster_name].iloc[0]
            
        elif raster_name in list(dfWMS.layer_name):
            # raster_name is the name of the wms layer
            
            # Get filename and filepath
            filename = dfWMS['filename'][dfWMS.layer_name == raster_name].iloc[0]
            filepath = dfWMS['filepath'][dfWMS.layer_name == raster_name].iloc[0]
            
            # Get target srs
            t_srs = dfWMS['t_srs'][dfWMS.layer_name == raster_name].iloc[0]
            
        elif raster_name in list(dfRasters.layer_name):
            
            # Get filename
            filename = dfRasters['filename'][dfRasters.layer_name == raster_name].iloc[0]
            filepath = dfRasters['filepath'][dfRasters.layer_name == raster_name].iloc[0]
            # Get target srs
            t_srs = 'from_tif' # Read the srs from the tif file
        
        
        # Search by raster file name
        if raster_name in list(dfLayers.filename):
            # raster_name is the name of the tif or jp2 file
            
            # Get filename and filepath
            filename = dfLayers['filename'][dfLayers.filename == raster_name].iloc[0]
            filepath = dfLayers['filepath'][dfLayers.filename == raster_name].iloc[0]
            # Get target srs
            # t_srs = dfWMS['t_srs'][dfWMS.filename == raster_name].iloc[0]
            t_srs = 'from_tif'
        
        
        else:
            # TODO: add case where filename is not from wms
            raise ValueError('{} raster not found.'.format(raster_name))

        # Get Fullfilename
        fullfilename = filepath / filename
        
        
        # 1. Read data from raster --------------------------------------------
        # Open the image using gdal
        ds = gdal.Open(str(fullfilename))
        
        
        # Extract the image data
        # Note: Cartopy/matplotlib requires the color bands to be in the last 
        # dimension of an array (i.e., row, col, band), wheras gdal data is in 
        # (band,row,col)? So we use np.transpose(im, [1,2,0]) to reorder the 
        # dimensions.
        
         # Image data as array of pixels
        img_data = ds.ReadAsArray()
        
        if len(img_data.shape) == 2:
            # Single band
            img = img_data # 2D image array
            # cmap = 'jet'        # Color map

            # Check for binary image
            if np.array_equal(img, img.astype(bool)):
                # cmap = mpl.colors.ListedColormap(["navy", "crimson", "limegreen", "gold"])
                # cmap = mpl.colors.ListedColormap(["crimson","limegreen"])
                cmap = mpl.colors.ListedColormap(["crimson","limegreen"])
                norm = mpl.colors.BoundaryNorm(np.arange(-0.5,4), cmap.N) 
            
        else:
            # Multiband data.
            img = img_data[:3, :, :].transpose((1, 2, 0)) # Reorder dimensions
            cmap = None # Use rgb values for color
            if img.shape[2] < 3:
                # Image only has 2 bands
                # Plot single band image as colormap
                cmap = 'gray'
                img = img[:,:,0] # Select first band only
                # img = newimg

        # Get nodata value of raster band (-9999.)
        nodataval = ds.GetRasterBand(1).GetNoDataValue() # Get nodata value from first band       
        # Replace nodataval with nan
        if (nodataval is not None) & (nodataval != 0.):
            try:
                img[img == nodataval] = np.nan
            except:
                # Integer values.
                if nodataval in img:
                    img[img == nodataval] = np.nan
                
        
        # Geotransform
        gt = ds.GetGeoTransform()
        # (x0, pixel width, x pixel rotation, y0,y pixel rotation, -pixel height)
        # use ApplyGeoTransform(gt,x,y) to convert pixel coordinates x,y to
        # lat,long coordinates
        
        # # Inverse transform (coords to image coords)
        # inv_gt = gdal.InvGeoTransform(gt) # (Not needed here)
        
        # Get image extent from transform (in srs)
        img_extent = (gt[0], gt[0] + ds.RasterXSize * gt[1],
                  gt[3] + ds.RasterYSize * gt[5], gt[3])
        
        
        # Projection in WKT
        proj_wkt = ds.GetProjection()
        # e.g. 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST],AUTHORITY["EPSG","4326"]]'
        # Note: WGS84 = EPSG4326 = PlateCarree
        # FIXME: No projection info when using reprojection with python bindings.
        
        # Convert projection to osr SpatialReference object
        inproj = osr.SpatialReference()
        inproj.ImportFromWkt(proj_wkt)
        
        # Proj4 string
        proj4_str = inproj.ExportToProj4()
        
        # 2. Set up cartopy parameters ----------------------------------------
        
        # Specify cartopy ellipsoid
        if self.planet in ['Luna','luna']:
            ellipsoid = ccrs.Globe(semimajor_axis=1737400, semiminor_axis=1737400,ellipse=None)
        if self.planet in ['Mars','mars']:
            ellipsoid = ccrs.Globe(semimajor_axis=3396190, semiminor_axis=3376200,ellipse=None)

        # TODO: Add ellipsoids of other planets
        
        # Specify cartopy crs projection
        if t_srs in ['EPSG:4326']:
            # EPSG:4326 == PlateCarree
            data_crs = ccrs.PlateCarree(globe=ellipsoid)     
        elif t_srs in ['IAU2000:30120','South Pole','South']:
            data_crs = ccrs.SouthPolarStereo(globe=ellipsoid)
            # Alternative: if 'stereo' in proj4_string
        elif t_srs == 'from_tif':
            # Get the crs from the tif
            
            # Create dictionary of proj4 parameters
            proj_crs = pyproj.crs.CRS.from_string(proj4_str)
            proj4_dict = proj_crs.to_dict() # proj4 params as dictionary
            
            # Create globe
            if '+a' in proj4_str:
                # Elipsoid
                if '+b' in proj4_str:
                    # Ellipsoid from semimajor and semiminor axes
                    ellipsoid = ccrs.Globe(semimajor_axis=proj4_dict['a'], semiminor_axis=proj4_dict['b'])
                elif '+rf' in proj4_str:
                    # Compute semiminor axes from inverse of flattening.
                    # b =  a(1 - f) = a(1 - 1/rf)
                    ellipsoid = ccrs.Globe(semimajor_axis = proj4_dict['a'], 
                                           semiminor_axis = proj4_dict['a']*(1 - 1/proj4_dict['rf']))
                
            elif '+R' in proj4_str:
                # Sphere
                ellipsoid = ccrs.Globe(semimajor_axis=proj4_dict['R'], semiminor_axis=proj4_dict['R'])
            
            elif '+datum=WGS84' in proj4_str:
                # Default earth reference ellipsoid
                ellipsoid = ccrs.Globe(ellipse='WGS84')
            
            # Create data crs from projection
            if (proj4_dict['proj'] == 'stere'):
                if (proj4_dict['lat_0'] == -90):
                    # South Pole Stereoscopic projection
                    data_crs = ccrs.SouthPolarStereo(globe=ellipsoid)
                elif (proj4_dict['proj'] == 'stere') & (proj4_dict['lat_0'] == -90):    
                    # North Pole Stereoscopic projection
                    data_crs = ccrs.NorthPolarStereo(globe=ellipsoid)
            elif (proj4_dict['proj'] == 'longlat'):
                # LAT/LONG coordinates
                data_crs = ccrs.PlateCarree(globe=ellipsoid)  
            elif (proj4_dict['proj'] == 'eqc'):
                # Equidistant Cylindrical (Plate Carrée)
                data_crs = ccrs.PlateCarree(globe=ellipsoid) 
            else:    
                # TODO: add additional cases.
                pdb.set_trace()
            
        
        # Create a new axes 
        fig = plt.figure() # figsize=(10, 5)
        ax = fig.add_subplot(1, 1, 1, projection=data_crs)
        plt.title(filename)
        
        # Add the image
        im = ax.imshow(img, origin='upper', extent=img_extent,alpha=alpha,
                        interpolation='nearest',
                        cmap=cmap,
                        transform=data_crs) # transform=crs of input data
        
        # Plot gridlines
        if showgrid is True:
            ax.gridlines(linewidth=0.5, color='gray', alpha=0.5, linestyle='--')
        
        # Add colorbar if numeric raster
        if len(img_data.shape) == 2:
            # Single band
            
            # Vertical colorbar
            divider = make_axes_locatable(ax)
            ax_cb = divider.new_horizontal(size="5%", pad=0.1, axes_class=plt.Axes)
            fig.add_axes(ax_cb)
            clb = plt.colorbar(im, cax=ax_cb)
            clb.ax.set_title('Value')
            # plt.tight_layout(h_pad=1)

        
        # # Embed in tkinter gui
        # root = Tk.Tk()
        # root.wm_title("Cartopy in TK")
        # # a tk.DrawingArea
        # canvas = FigureCanvasTkAgg(fig, master=root)
        # # canvas.show()
        # canvas.get_tk_widget().pack(side=Tk.TOP, fill=Tk.BOTH, expand=1)
        # canvas._tkcanvas.pack(side=Tk.TOP, fill=Tk.BOTH, expand=1)
        # # button = Tk.Button(master=root, text='Quit', command=sys.exit)
        # # button.pack(side=Tk.BOTTOM)
        # Tk.mainloop()
        
        
        # Add shapefile
        if shape_name is not None:
            
            # Read shapefile data from .dbf
            gdf = self.get_shapes(shape_name, match_proj=raster_name)
            
            # Filter by extent using spatial indexer .cx
            # Example: Focusing on a specific region
            extent = [self.long_min, self.long_max, self.lat_min, self.lat_max] 
            gdf_sub = gdf.cx[extent[0]:extent[1], extent[2]:extent[3]]
            
            
            # # Create a colormap for shapes
            # import matplotlib.cm as cm
            # cmap = cm.get_cmap('viridis', len(gdf_sub))
            
            # # Iterate and plot with different colors
            # for i, (index, row) in enumerate(gdf_sub.iterrows()):
            #     ax.add_geometries([row['geometry']], crs=ccrs.PlateCarree(globe=ellipsoid),
            #                       facecolor=cmap(i), edgecolor='black', alpha=alpha_shp)
            
            
            # Create a colormap for shapes
            # Use: https://imagecolorpicker.com/
            import matplotlib.cm as cm
            cmap = cm.get_cmap('viridis', len(gdf_sub))
            color_dict = {'Ccc':'#fadc02',
                          'Csc':'#ffffbe',
                          'Ec': '#a5ce30',
                          'Ecc': '#6ec400',
                          'Esc':'#6ec400',
                          'Em': '#f10d0c',
                          'EIp':'#e54d74',
                          'Ic': '#6b20df',
                          'Ic1':'#2116f8',
                          'Ic2':'#1c7cf7',
                          'Icc':'#97dbf2',
                          'Isc':'#004da7',
                          'Icf':'#f28bb8',
                          'Ib':'#44648a',
                          'Ibm':'#bc424d',
                          'Id':'#ff3600',
                          'Ig':'#73b2c3',
                          'Iia':'#2a5ed4',
                          'Iiap': '#6f4489',
                          'Iic':'#1091ca',
                          'Iif':'#aa58e0',
                          'Im1':'#e400c5',
                          'Im2':'#fe3362',
                          'Imd':'#fc029a',
                          'Iohi':'#a6d5ff',
                          'Ioho':'#c4e8ff',
                          'Ios':'#00abb3',
                          'Iom':'#7795db',
                          'Iork':'#52b9fc',
                          'Iorm':'#465fb9',
                          'Ip':'#caa4cd',
                          'It':'#cda7f0',
                          'Itd':'#02aff1',
                          'INp':'#73b2c3',
                          'INt':'#cbacaa',
                          'Nc':'#c96936',
                          'Nb':'#f4c784',
                          'Nbl':'#ffcdba',
                          'Nbm':'#ffccbe',
                          'Nbsc':'#f3a263',
                          'Nnj':'#ffffbe',
                          'Np':'#f0bcae',
                          'Nt':'#fbd5d4',
                          'Ntp':'#efbfcf',
                          'pNb':'#64442f',
                          'pNbm':'#64442f',
                          'pNc':'#7b3e29',
                          'pNt':'#dd9f92'
                          }
            
            # Iterate and plot with different colors
            for i, (index, row) in enumerate(gdf_sub.iterrows()):
                unit = row['FIRST_Unit'] # Get unit
                ax.add_geometries([row['geometry']], crs=ccrs.PlateCarree(globe=ellipsoid),
                                  facecolor=color_dict[unit], edgecolor='black', alpha=alpha_shp)
            
        
        return
    
    def plot_craters_cartopy(self,basemap=None, min_diam=None, cmap='jet', showgrid=True, alpha=1.):
        
        
        # Alias raster_name
        raster_name = basemap
        
        # Set default basemap
        if raster_name is None:
            raster_name = self.rasters[0]
        
        
        # Load list of WMS rasters
        dfWMS = self.list_wms_layers()
        dfRasters = self.list_raster_layers()
        dfLayers = self.list_all_layers()
        
        
        # Get Filename and filepath
        # TODO: Replace this code block with the self.get_raster_filename method
        
        # Check if raster_name is in dfWMS and get filename
        if raster_name in list(dfWMS.filename):
            # raster_name is the name of the tif file
            
            # Get filename and filepath
            filename = dfWMS['filename'][dfWMS.filename == raster_name].iloc[0]
            filepath = dfWMS['filepath'][dfWMS.filename == raster_name].iloc[0]
            # Get target srs
            t_srs = dfWMS['t_srs'][dfWMS.filename == raster_name].iloc[0]
            
            
            
        elif raster_name in list(dfWMS.layer_name):
            # raster_name is the name of the wms layer
            
            # Get filename and filepath
            filename = dfWMS['filename'][dfWMS.layer_name == raster_name].iloc[0]
            filepath = dfWMS['filepath'][dfWMS.layer_name == raster_name].iloc[0]
            
            # Get target srs
            t_srs = dfWMS['t_srs'][dfWMS.layer_name == raster_name].iloc[0]
            
            
        elif raster_name in list(dfRasters.layer_name):
            
            # Get filename
            filename = dfRasters['filename'][dfRasters.layer_name == raster_name].iloc[0]
            filepath = dfRasters['filepath'][dfRasters.layer_name == raster_name].iloc[0]
            # Get target srs
            t_srs = 'from_tif' # Read the srs from the tif file
        
        
        # Search by raster file name
        if raster_name in list(dfLayers.filename):
            # raster_name is the name of the tif or jp2 file
            
            # Get filename and filepath
            filename = dfLayers['filename'][dfLayers.filename == raster_name].iloc[0]
            filepath = dfLayers['filepath'][dfLayers.filename == raster_name].iloc[0]
            # Get target srs
            # t_srs = dfWMS['t_srs'][dfWMS.filename == raster_name].iloc[0]
            t_srs = 'from_tif'
        
        
        else:
            # TODO: add case where filename is not from wms
            raise ValueError('{} raster not found.'.format(raster_name))
        
        # Get Fullfilename
        fullfilename = filepath / filename
        
        
        # 1. Read data from raster --------------------------------------------
        # Open the image using gdal
        ds = gdal.Open(str(fullfilename))
        
        
        # Extract the image data
        # Note: Cartopy/matplotlib requires the color bands to be in the last 
        # dimension of an array (i.e., row, col, band), wheras gdal data is in 
        # (band,row,col)? So we use np.transpose(im, [1,2,0]) to reorder the 
        # dimensions.
        
         # Image data as array of pixels
        img_data = ds.ReadAsArray()
        
        if len(img_data.shape) == 2:
            # Single band
            img = img_data # 2D image array
            # cmap = 'jet'        # Color map
            
            # Check for binary image
            if np.array_equal(img, img.astype(bool)):
                # cmap = mpl.colors.ListedColormap(["navy", "crimson", "limegreen", "gold"])
                # cmap = mpl.colors.ListedColormap(["crimson","limegreen"])
                cmap = mpl.colors.ListedColormap(["crimson","limegreen"])
                norm = mpl.colors.BoundaryNorm(np.arange(-0.5,4), cmap.N) 
            
        else:
            # Multiband data.
            img = img_data[:3, :, :].transpose((1, 2, 0)) # Reorder dimensions
            cmap = None # Use rgb values for color
            if img.shape[2] < 3:
                # Image only has 2 bands
                # Plot single band image as colormap
                cmap = 'gray'
                img = img[:,:,0] # Select first band only
                # img = newimg
        
        # Get nodata value of raster band (-9999.)
        nodataval = ds.GetRasterBand(1).GetNoDataValue() # Get nodata value from first band       
        # Replace nodataval with nan
        if (nodataval is not None) & (nodataval != 0.):
            try:
                img[img == nodataval] = np.nan
            except:
                # Integer values.
                if nodataval in img:
                    img[img == nodataval] = np.nan
                
        
        # Geotransform
        gt = ds.GetGeoTransform()
        # (x0, pixel width, x pixel rotation, y0,y pixel rotation, -pixel height)
        # use ApplyGeoTransform(gt,x,y) to convert pixel coordinates x,y to
        # lat,long coordinates
        
        # # Inverse transform (coords to image coords)
        # inv_gt = gdal.InvGeoTransform(gt) # (Not needed here)
        
        # Get image extent from transform (in srs)
        img_extent = (gt[0], gt[0] + ds.RasterXSize * gt[1],
                  gt[3] + ds.RasterYSize * gt[5], gt[3])
        
        
        # Projection in WKT
        proj_wkt = ds.GetProjection()
        # e.g. 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST],AUTHORITY["EPSG","4326"]]'
        # Note: WGS84 = EPSG4326 = PlateCarree
        # FIXME: No projection info when using reprojection with python bindings.
        
        # Convert projection to osr SpatialReference object
        inproj = osr.SpatialReference()
        inproj.ImportFromWkt(proj_wkt)
        
        # Proj4 string
        proj4_str = inproj.ExportToProj4()
        
        # 2. Set up cartopy parameters ----------------------------------------
        
        # Specify cartopy ellipsoid
        if self.planet in ['Luna','luna']:
            ellipsoid = ccrs.Globe(semimajor_axis=1737400, semiminor_axis=1737400,ellipse=None)
        if self.planet in ['Mars','mars']:
            ellipsoid = ccrs.Globe(semimajor_axis=3396190, semiminor_axis=3376200,ellipse=None)
        # TODO: Add ellipsoids of other planets
        
        # Specify cartopy crs projection
        if t_srs in ['EPSG:4326']:
            # EPSG:4326 == PlateCarree
            data_crs = ccrs.PlateCarree(globe=ellipsoid)     
        elif t_srs in ['IAU2000:30120','South Pole','South']:
            data_crs = ccrs.SouthPolarStereo(globe=ellipsoid)
            # Alternative: if 'stereo' in proj4_string
        elif t_srs == 'from_tif':
            # Get the crs from the tif
            
            
            # Create dictionary of proj4 parameters
            proj_crs = pyproj.crs.CRS.from_string(proj4_str)
            proj4_dict = proj_crs.to_dict() # proj4 params as dictionary
            
            # Create globe
            if '+a' in proj4_str:
                # Elipsoid
                if '+b' in proj4_str:
                    # Ellipsoid from semimajor and semiminor axes
                    ellipsoid = ccrs.Globe(semimajor_axis=proj4_dict['a'], semiminor_axis=proj4_dict['b'])
                elif '+rf' in proj4_str:
                    # Compute semiminor axes from inverse of flattening.
                    # b =  a(1 - f) = a(1 - 1/rf)
                    ellipsoid = ccrs.Globe(semimajor_axis = proj4_dict['a'], 
                                           semiminor_axis = proj4_dict['a']*(1 - 1/proj4_dict['rf']))
                
            elif '+R' in proj4_str:
                # Sphere
                ellipsoid = ccrs.Globe(semimajor_axis=proj4_dict['R'], semiminor_axis=proj4_dict['R'])
            
            # Create data crs from projection
            if (proj4_dict['proj'] == 'stere'):
                if (proj4_dict['lat_0'] == -90):
                    # South Pole Stereoscopic projection
                    data_crs = ccrs.SouthPolarStereo(globe=ellipsoid)
                elif (proj4_dict['proj'] == 'stere') & (proj4_dict['lat_0'] == -90):    
                    # North Pole Stereoscopic projection
                    data_crs = ccrs.NorthPolarStereo(globe=ellipsoid)
            elif (proj4_dict['proj'] == 'longlat'):
                # LAT/LONG coordinates
                data_crs = ccrs.PlateCarree(globe=ellipsoid)  
            elif (proj4_dict['proj'] == 'eqc'):
                # Equidistant Cylindrical (Plate Carrée)
                data_crs = ccrs.PlateCarree(globe=ellipsoid) 
            else:    
                # TODO: add additional cases.
                pdb.set_trace()
            
        
        # Create a new axes 
        fig = plt.figure() # figsize=(10, 5)
        ax = fig.add_subplot(1, 1, 1, projection=data_crs)
        plt.title(filename)
        
        # Add the image
        im = ax.imshow(img, origin='upper', extent=img_extent,alpha=alpha,
                        interpolation='nearest',
                        cmap=cmap,
                        transform=data_crs) # transform=crs of input data
        
        # Plot gridlines
        if showgrid is True:
            ax.gridlines(linewidth=0.5, color='gray', alpha=0.5, linestyle='--')
        
        # Add colorbar if numeric raster
        if len(img_data.shape) == 2:
            # Single band
            
            # Vertical colorbar
            divider = make_axes_locatable(ax)
            ax_cb = divider.new_horizontal(size="5%", pad=0.1, axes_class=plt.Axes)
            fig.add_axes(ax_cb)
            clb = plt.colorbar(im, cax=ax_cb)
            clb.ax.set_title('Value')
            # plt.tight_layout(h_pad=1)
        
        # Add craters
        
        # if add_craters == True:
            
        # Get the craters
        dfcraters = self.craters
        
        # Filter crater diameters
        if min_diam is not None:
            
            if self.planet in ['Luna','Moon']:
                dfcraters = dfcraters[dfcraters.DIAM_C_IM >= min_diam]
            elif self.planet in ['Mars']:
                pass
        
                
        
        
        # Transform geometry to crs of raster
        dfcraters = dfcraters.to_crs(proj4_str)
        
        # ax.add_geometries(dfcraters['geometry'], crs=ccrs.PlateCarree(globe=ellipsoid) )
                          # # facecolor='white', edgecolor='black',
                          # , color='r')
        
        dfcraters.plot(ax=ax)
        
        
        
        # # Embed in tkinter gui
        # root = Tk.Tk()
        # root.wm_title("Cartopy in TK")
        # # a tk.DrawingArea
        # canvas = FigureCanvasTkAgg(fig, master=root)
        # # canvas.show()
        # canvas.get_tk_widget().pack(side=Tk.TOP, fill=Tk.BOTH, expand=1)
        # canvas._tkcanvas.pack(side=Tk.TOP, fill=Tk.BOTH, expand=1)
        # # button = Tk.Button(master=root, text='Quit', command=sys.exit)
        # # button.pack(side=Tk.BOTTOM)
        # Tk.mainloop()
        
        
        return
    
    
    
    
        
    # Display methods --------------------------------------------
    def __repr__(self):
        return "PlanetaryRegion('{}')".format(self.name)
    
    def __str__(self):
        return str(pprint(vars(self)))
    

# TODO: Crater Detection algorithm: PyCDA https://github.com/AlliedToasters/PyCDA


#%% ###########################################################################
#                       Planetary Terrain DEM
# #############################################################################
        
class PlanetaryTerrain:
    '''
    3D Terrain Mesh/Resource model of a planetary region.
    
    Methods to generate and display a 3d mesh, including different raster layers.
    
    '''
    
    def __init__(self):
        
        # Set default properties
        self.type = 'Planetary Terrain'
        self.planet = None # Parent planet
        self.longlat_proj4 = None # IAU2000 type srs for lat/long coordinates
        self.gravity_model = 'Point_Mass'  # Gravity model
        self.material = None
        
        # DEM data
        self.demfile = None   # Filename of dem
        self.dempath = None   # Filepath of dem
        self.demunits = None
        self.dem_proj4 = None # Proj4 string of demfile
        self.dem_wtk = None   # WKT string of dem
        
        # Mesh data
        self.units = 'km'     # Units of mesh
        self.meshtype = None  # Meshtype (pyvista, vtk)
        self.mesh_frame = None # Reference frame of mesh (raster,ENU,ECEF)
        self.mesh = None       # Surface mesh
        self.grid = None   
        self.volmesh = None   # Volume mesh
        
        
    # Constructor methods -----------------------------------------------------
    @classmethod
    def from_dem(cls,demfilepath, demfile, meshtype='pyvista', units='m', # Required 
                       planet = None,
                       mesh_frame = None, 
                       material=None):
        '''
        Construct a model from a dem file

        Parameters
        ----------
        cls : TYPE
            DESCRIPTION.
        demfilepath : TYPE
            DESCRIPTION.
        demfile : TYPE
            DESCRIPTION.
        # Required                       material : TYPE, optional
            DESCRIPTION. The default is None.

        Returns
        -------
        None.

        '''
        
        
        # Set default mesh_frame
        if mesh_frame is None:
            mesh_frame = 'raster'
        
        # Get full filename of DEM
        fullfilename = demfilepath / demfile
        # fullfilename = demfilepath + demfile
        
        # Check if file exists
        if fullfilename.is_file() == False:
            raise ValueError('DEM file {} does not exist.'.format(demfile))
        
        # Convert filename to string
        fullfilename = str(fullfilename)
        
        # Construct
        cls = PlanetaryTerrain() # Instantiate
        cls.planet = planet      # Add parent planet object
        
        # Set latlon srs of planet
        if planet in ['Luna','Moon']:
            # IAU2000:30100
            cls.longlat_proj4 = '+proj=longlat +a=1737400 +b=1737400 +no_defs '
        elif planet in ['Mars']:
            # IAU2000:49900
            cls.longlat_proj4 = '+proj=longlat +a=3396190 +b=3376200 +no_defs '
        else:
            # TODO: add for other planets
            cls.longlat_proj4 = None
            
        
        
        # DEM Data ------------------------------------------------------------
        
        
        # Read dem file data
        
        # Open using gdal    
        ds = gdal.Open(fullfilename) # Open file
        
        # Projection in WKT
        proj_wkt = ds.GetProjection()
        # e.g. 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST],AUTHORITY["EPSG","4326"]]'
        # Note: WGS84 = EPSG4326 = PlateCarree
        
        # Convert projection to osr SpatialReference object
        inproj = osr.SpatialReference()
        inproj.ImportFromWkt(proj_wkt)
        
        # Get bbox
        gt = ds.GetGeoTransform()
        img_extent = (gt[0], gt[0] + ds.RasterXSize * gt[1],
                      gt[3] + ds.RasterYSize * gt[5], gt[3])
        
        minx = img_extent[0] # gt[0]
        maxx = img_extent[1]  # minx + ds.RasterXSize *gt[1]
        miny = img_extent[2]  # gt[3] + ysize *gt[5]
        maxy = gt[3]
        
        bbox = (minx,miny,maxx,maxy) # *** Differnet ordering required for shapely
        
        # Convert to shapely geometry
        geom = shapely.geometry.box(*bbox) # minx,miny,maxx,maxy
        
        
        # Proj4 string
        inproj_proj4 = inproj.ExportToProj4() 
        
        # Append dem data
        cls.demfile = demfile        # File name of dem raster
        cls.dempath = demfilepath    # File path of dem raster
        cls.demunits = units         # Units of dem
        cls.dem_proj4 = inproj_proj4 # Proj4 string
        cls.dem_wtk = proj_wkt       # WKT string
        cls.dem_gt = gt              # DEM geotransform
        cls.dem_bbox_geom = geom     # Geometry of bounding box (in dem_proj4)
        ds = None # Save and close demfile
        
        # Mesh Data -----------------------------------------------------------
        
        # Generate Mesh
        # mesh = mesh_from_dem(fullfilename, planet_name, meshtype, mesh_frame=mesh_frame) # Set mesh
        mesh = cls.GetMesh(meshtype,mesh_frame)
        
        # Append mesh data
        cls.mesh = mesh
        cls.meshtype = meshtype
        # cls.mesh_srs = mesh_srs
        cls.mesh_frame = mesh_frame
        
        
        
        # # Generate grid
        # top = mesh.points.copy()
        # bottom = mesh.points.copy()
        # depth = 10000.0 # depth
        # bottom[:,-1] = -10.0 # Wherever you want the plane
        # vol = pv.StructuredGrid()
        # vol.points = np.vstack((top, bottom))
        # vol.dimensions = [*mesh.dimensions[0:2], 2]
        # cls.volmesh = vol
        
        
        # # Terrain following mesh
        # # z_cells = np.array([1000]*5 + [5000]*3 + [10000]*2) # depth coords (km)
        # z_cells = np.array([0.1]*10)
        # xx = np.repeat(mesh.x, len(z_cells), axis=-1)
        # yy = np.repeat(mesh.y, len(z_cells), axis=-1)
        # zz = np.repeat(mesh.z, len(z_cells), axis=-1) - np.cumsum(z_cells).reshape((1, 1, -1))
        
        # volmesh = pv.StructuredGrid(xx, yy, zz)
        # volmesh["Elevation"] = zz.ravel(order="F")
        # cls.volmesh = volmesh
        
        return cls
    
    # Converting reference frame ----------------------------------------------
    def convert_frame(self,mesh_frame):
        
        # Create and return a new instance of the mesh
        # see: https://stackoverflow.com/questions/15548886/how-can-i-make-a-class-method-return-a-new-instance-of-itself
        
        
        # Check for valid input
        if mesh_frame not in ['raster','ENU','ECEF']:
            raise ValueError("Invalid mesh frame. Choose from ['raster','ENU','ECEF'] ")
        
        # Get the current mesh reference frame
        curr_frame = self.mesh_frame
        
        if curr_frame == mesh_frame:
            # Mesh already in desired reference
            print('Mesh already in desired reference frame.')
        
        else:
            # Re-generate mesh with desired reference frame
            print('Converting mesh to {}'.format(mesh_frame))
            newterrain = self.__class__.from_dem(self.dempath, self.demfile, meshtype=self.meshtype, units=self.demunits, # Required 
                       planet = self.planet,
                       mesh_frame = mesh_frame, 
                       material=None)
            
            # Replace instance
            self.__dict__.update(newterrain.__dict__)
            
            # # Alternatively, Update mesh.points and mesh.faces
            # self.mesh.points = newterrain.mesh.points
            # # Need to replace more than just the points
            
        return
    
    def convert_meshtype(self,meshtype):
        
        if self.meshtype == meshtype:
            print('Mesh already in desired meshtype.')
        else:
            # Regenerate mesh with desired meshtype
            print('Converting meshtype to {}'.format(meshtype))
            newterrain = self.__class__.from_dem(self.dempath, self.demfile, meshtype=meshtype, units=self.demunits, # Required 
                       planet = self.planet,
                       mesh_frame = self.mesh_frame, 
                       material=None)
            # Replace instance
            self.__dict__.update(newterrain.__dict__)
            # *** Alternatively, changed parameters in existing instance
            
        
        return
    
    # Getters -----------------------------------------------------------------
    def GetMesh(self,meshtype='pyvista',mesh_frame='raster'):
        '''
        Generate a Mesh object.

        Parameters
        ----------
        meshtype : TYPE, optional
            DESCRIPTION. The default is 'pyvista'.
        mesh_frame : TYPE, optional
            DESCRIPTION. The default is 'raster'.

        Returns
        -------
        mesh : TYPE
            DESCRIPTION.

        '''
        
        # TODO:
        # Read the DEM file to create and return an instance of a mesh object.
        # Do this on command, rather than store as attribute?
        # Use this method as a mesh constructor. Can choose to append mesh later.
        
        # Get the planet name
        if type(self.planet) == str:
            planet_name = self.planet
        else:
            planet_name = self.planet.name
        
        # Generate the mesh
        fullfilename = self.dempath/self.demfile
        mesh = mesh_from_dem(str(fullfilename), planet_name, meshtype, mesh_frame=mesh_frame, units=self.demunits) # Set mesh
        
        
        return mesh
    
    
    def get_dem_ds(self):
        
        
        # Open the image using gdal
        fullfilename = self.dempath/self.demfile
        ds = gdal.Open(str(fullfilename))
        
        return ds
        
    
    def get_craters(self):
        '''
        Get a list of craters within the bounds of the terrain dem.

        '''
        
        # Get bbox of the terrain mesh
       
        
        # bbox_geom = shapely.geometry.box(*self.bbox)
        
        # Get List of craters
        if self.planet in ['Luna','Moon']:
            # Get Lunar Crater Database
            # gdf = LunarCraterDB.import_moon_craters_LU78287GT()
            gdf = LunarCraterDB.import_moon_craters_robbins()
            
        elif self.planet in ['Mars']:
            # Get Mars Crater Database
            # gdf = LunarCraterDB.import_mars_craters_MA132843GT()
            gdf = LunarCraterDB.import_mars_craters_robbins()
        else:
            # TODO: Add other crater databases
            return None
        
        # Reset crs
        gdf.crs = self.longlat_proj4
        
        # Get bbox of dem as geodataframe
        bbox_df = gpd.GeoDataFrame(gpd.GeoSeries(self.dem_bbox_geom), columns=['geometry'],crs=self.dem_proj4)
        bbox_longlat = bbox_df.copy()
        
        bbox_longlat['geometry'] = bbox_longlat['geometry'].to_crs(crs = self.longlat_proj4) # Convert to longlat coords
        
        
        # # Alternative method
        # dfcraters2 = gpd.overlay(gdf, bbox_longlat, how='intersection')
        
        # pdb.set_trace()
        
        
        
        
        # Set geometry
        # df2 = gdf.set_geometry("buffered")
        
        # Create a copy of the original geometry
        # latlon_geom = gdf['geometry'].copy()
        gdf['geometry_longlat'] = gdf['geometry']
        
        
        # Reproject crater coordinates to dem_srs
        gdf = gdf.set_geometry("geometry") # Set geometry
        gdf['geometry'] = gdf['geometry'].to_crs(crs = self.dem_proj4)
        
        
        # Find subset of craters within the geometry
        dfcraters = gpd.overlay(gdf, bbox_df, how='intersection')
        
        # TODO: Convert points to ECEF and ENU
        
        
        
        
        # # Reproject geometry to target srs
        # t_srs_str = '+proj=stere +lat_0=-90 +lon_0=0 +k=1 +x_0=0 +y_0=0 +a=1737400 +b=1737400 +units=m +no_defs '
        # dfnomen['geometry_spstereo'] = dfnomen['geometry'].to_crs(crs = t_srs_str)
        
        
        
        
        return dfcraters
    
    # Plotting ----------------------------------------------------------------
    def plot_pv(self, texture=None, notebook=False,*args):
        '''
        Generate a 3D plot of the surface using PyVista.

        Parameters
        ----------
        texture : TYPE, optional
            DESCRIPTION. The default is None.
        notebook : TYPE, optional
            DESCRIPTION. The default is False.
        *args : TYPE
            DESCRIPTION.

        Returns
        -------
        None.

        '''
        
        # Get the mesh
        mesh = self.mesh
        
        # Set up the plot
        p = pv.Plotter(notebook=notebook)
        
        # Plot the surface mesh as wireframe
        #p.add_mesh(half_ast, color='w', show_edges=True)
        
        color = 0.3*np.array([1,1,1])
        alpha = 1.0
        
        
        # p.add_mesh(mesh, color=color, style='surface', opacity=alpha,
        #             show_edges=True,edge_color='k', line_width=0.5)
        p.add_mesh(mesh, texture=texture, cmap=plt.cm.get_cmap("jet"), *args)
        
        # Add planet mesh
        if (self.planet is not None) & (self.mesh_frame == 'ECEF'):
            # TODO: Consider removing this.
            # check if parent is string or Planet object
            
            # Convert plane
            if type(self.planet) == str:
                self.planet = Planet(self.planet)
            
            planet_mesh = self.planet.surface.grid
            alpha = 1.
            p.add_mesh(planet_mesh,color=color, style='surface', opacity=alpha,
                   show_edges=True,edge_color='k', line_width=0.5)
        
        
        
        # Add axes
        p.add_axes()
        # p.add_legend()
        p.show()
        
        return 
    
    def plot_vtk(self, texture=None, notebook=False, export_html=False ,*args):
        '''
        Generate a 3D plot of the surface using Vedo (VTK).

        Parameters
        ----------
        texture : TYPE, optional
            DESCRIPTION. The default is None.
        notebook : TYPE, optional
            DESCRIPTION. The default is False.
        export_html : TYPE, optional
            DESCRIPTION. The default is False.
        *args : TYPE
            DESCRIPTION.

        Returns
        -------
        None.

        '''
        
        # TODO: Add alternative controler
        # see: https://semisortedblog.wordpress.com/2014/09/04/building-vtk-user-interfaces-part-3c-vtk-interaction/
        
        # Check if meshtype is vtk
        if self.meshtype != 'vtk':
            # Convert mesh
            self.convert_meshtype('vtkplotter')
        
        # Create plotter object
        # vp = vtkplotter.Plotter(bg='black')
        vp = vedo.Plotter(bg='black')
        
        # import k3d
        # vp = k3d.plot()
        
        # Turnoff embedding
        if notebook == False:
            # vtkplotter.embedWindow(False)
            # vedo.embedWindow(False) # Popup
            #vedo.embedWindow('k3d') # Embed in html
            vedo.settings.default_backend = 'k3d' 
        
        
        
        
        
        
        # Set colormap for mesh
        if texture == None:
            
            # Add Actors
            # mesh = self.mesh # Terrain mesh actor
            if self.meshtype == 'vtkplotter':
                mesh = self.mesh # Vedo mesh
            else:
                pdb.set_trace()
            
            # Default color - use elevation color map
            # (Not working)
            # elev = mesh.getPointArray('Elevation') # Get the elevation array
            elev = mesh.pointdata["Elevation"] # Get the elevation array
            mesh.cmap("jet", elev)
            # See: https://github.com/marcomusy/vedo/blob/master/examples/basic/mesh_coloring.py
            
            # Add scalar bar
            # mesh.addScalarBar(c='k',title='Elevation (km)',horizontal=True,titleFontSize=18)
            # mesh.scalarbar.SetWidth(0.3)
            # mesh.addScalarBar3D(c='w',title="Elevation (km)") # 3D version
            vp.add_scale_indicator()

        else:
            
            if self.meshtype == 'vtkplotter':
                mesh = self.mesh # Vedo mesh
            else:
                pdb.set_trace()
            
            # Get fullfilename
            filename = texture
            mesh, uv = add_texture_vtkplotter(mesh,str(filename))
            # mesh = vedo.mesh.Mesh(mesh) # Terrain mesh actor
            
            # mesh.texture(tname=str(filename),repeat=False)
            # mesh.texture('wood1') # Works
            
            # _file = r'C:\Chrono\data_chrono6\data\textures\bluewhite.png'
            # mesh.texture(tname=str(_file),tcoords=uv,repeat=False) # Works
            
            
            
        
        # Name the object
        mesh.name='Planetary Terrain'
        mesh.flat() # Set flat shading
        # Add mesh to plotter
        vp.add(mesh)
        
        
        # Add global axis in corner
        #vp.addGlobalAxes(axtype=4, c=None)
        vp.add_global_axes(axtype=4, c=None)
        
        # Add legend
        if export_html == False:
            #vp.addHoverLegend()
            vp.add_hover_legend()
        
        # # Add lighting
        # vp.addLight(pos=(1E9,0,0), focalPoint=(0, 0, 0), deg=180, 
        #     c='white', intensity=1.0, removeOthers=True, showsource=False)
        
       
        
        # Add button widget ------------------------------------------
        # https://github.com/marcomusy/vedo/blob/master/examples/basic/buttons.py
        
        # # Hide/show mesh button
        # def buttonfunc():
        #     mesh.alpha(1 - mesh.alpha())  # toggle mesh transparency
        #     bu.switch()                 # change to next status
        #     # printc(bu.status(), box="_", dim=True)
        # # Create button
        # bu = vp.addButton(
        #     buttonfunc,
        #     pos=(0.90, 0.95),  # x,y fraction from bottom left corner
        #     states=["Hide mesh", "Show mesh"],
        #     c=["w", "w"],
        #     bc=["dg", "dv"],  # colors of states
        #     font="courier",   # arial, courier, times
        #     size=18,
        #     bold=True,
        #     italic=False,
        # )
        
        # # Toggle camera button
        # interactorstyles = ["TrackballCamera", "TrackballActor","JoystickCamera"]
        # interactorint = [0,1,2]
        # interactor_dict = dict(zip(interactorstyles,interactorint))
        # def buttonfunc2():
        #     # Get the state
        #     cur_state = bu2.status() # Current state (string)
        #     cur_int = interactor_dict[cur_state] # Current state (int)
        #     # Get next state
        #     if cur_int == max(interactorint):
        #         next_int = 0 # Restart from first
        #     else:
        #         next_int = cur_int + 1
            
        #     # vp.show(interactorStype=next_int)
                
        #     # # Change interactor style
        #     # if next_int == 0:
        #     #     # TrackballCamera
        #     #     vp.interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballCamera())
        #     # elif next_int == 1:
        #     #     # TrackballActor
        #     #     vp.interactor.SetInteractorStyle(vtk.vtkInteractorStyleTrackballActor())
        #     # elif next_int == 2:
        #     #     vp.interactor.SetInteractorStyle(vtk.vtkInteractorStyleJoystickCamera())
            
        #     bu2.switch()                 # change to next status
        #     # printc(bu.status(), box="_", dim=True)
        # # Create button
        # bu2 = vp.addButton(
        #     buttonfunc2,
        #     pos=(0.70, 0.95),  # x,y fraction from bottom left corner
        #     states=interactorstyles,
        #     c=["w", "w","w"],
        #     bc=["dg", "dv","dv"],  # colors of states
        #     font="courier",   # arial, courier, times
        #     size=18,
        #     bold=True,
        #     italic=False,
        # )
        
        
        # # Add text caption
        # if export_html == False:
        #     caption_text = 'PlanetaryTerrain \n' + 'Planet: ' + self.planet + '\n'  + 'Frame: ' + self.mesh_frame
        #     caption = vedo.Text2D(caption_text, pos=3)
        #     vp.add(caption)

        
        # Show
        if export_html == False:
            #vp.show(interactorStyle=0)
            vp.show(mode=0)
            # 0 = TrackballCamera [default] - 1 = TrackballActor - 
            # 2 = JoystickCamera - 3 = JoystickActor - 4 = Flight - 
            # 5 = RubberBand2D - 6 = RubberBand3D - 7 = RubberBandZoom - 
            # 8 = Context - 9 = 3D -10 = Terrain -11 = Unicam
            
            # Show with camera location
            # startcam_dict = {'pos':(0,0,2*moon_rad),'focalPoint':(0,0,moon_rad),'viewup':(0,1,0)}
            # vp.show(camera=startcam_dict) 
            
        # Export to html
        elif export_html == True:
            vp.reset_camera()
            #vedo.exportWindow('terrain.html')
            vedo.export_window('terrain.html')
        
        
        return
    
    def plot_dash(self):
        
        # See: https://github.com/plotly/dash-vtk/blob/master/demos/pyvista-terrain-following-mesh/app.py
        
        # Note: 1st element of lines and polys in dash-vtk is the number
        # e.g lines = [3,0,1,2] is a line with 3 vertices 0->1->2
        
        
        # Get the required data
        def updateWarp(factor=1):
            terrain = self.mesh.warp_by_scalar(factor=factor) # PyVista StructuredGrid or UniformGrid
            # Threshold the mesh to remove nan points
            lim = [np.nanmin(terrain['Elevation']),np.nanmax(terrain['Elevation'])]
            terrain = terrain.threshold(lim,'Elevation')
            
            # Extract polydata
            polydata = terrain.extract_geometry()
            
            points = polydata.points.ravel() # Set of points
            points[np.isnan(points)] = 0. # Replace nan with 0
            polys = vtk_to_numpy(polydata.GetPolys().GetData()) # Polys
            # elevation = polydata["scalar1of1"]
            elevation = polydata["Elevation"]
            min_elevation = np.amin(elevation)
            max_elevation = np.amax(elevation)
            
            return [points, polys, elevation, [min_elevation, max_elevation]]
        
        def toDropOption(name):
            return {"label": name, "value": name}
        
        
        points, polys, elevation, color_range = updateWarp(1)
        
        # Setup VTK rendering of PointCloud
        app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        server = app.server
        
        # Generate a View component
        vtk_view = dash_vtk.View(
            id="vtk-view",
            # Add components
            children=[
                dash_vtk.GeometryRepresentation(
                    id="vtk-representation",
                    children=[
                        dash_vtk.PolyData(
                            id="vtk-polydata",
                            points=points,
                            polys=polys,
                            children=[
                                dash_vtk.PointData(
                                    [
                                        dash_vtk.DataArray(
                                            id="vtk-array",
                                            registration="setScalars",
                                            name="elevation",
                                            values=elevation,
                                        )
                                    ]
                                )
                            ],
                        )
                    ],
                    colorMapPreset="erdc_blue2green_muted",
                    colorDataRange=color_range,
                    property={"edgeVisibility": True,},
                )
            ],
        )

        app.layout = dbc.Container(
            fluid=True,
            style={"height": "100vh"},
            children=[
                dbc.Row(
                    [
                        dbc.Col(
                            children=dcc.Slider(
                                id="scale-factor",
                                min=0.1,
                                max=5,
                                step=0.1,
                                value=1,
                                marks={0.1: "0.1", 5: "5"},
                            )
                        ),
                        dbc.Col(
                            children=dcc.Dropdown(
                                id="dropdown-preset",
                                options=list(map(toDropOption, presets)),
                                value="erdc_rainbow_bright",
                            ),
                        ),
                    ],
                    style={"height": "12%", "align-items": "center"},
                ),
                html.Div(
                    html.Div(vtk_view, style={"height": "100%", "width": "100%"}),
                    style={"height": "88%"},
                ),
            ],
        )
        
        
        @app.callback(
            [
                Output("vtk-representation", "colorMapPreset"),
                Output("vtk-representation", "colorDataRange"),
                Output("vtk-polydata", "points"),
                Output("vtk-polydata", "polys"),
                Output("vtk-array", "values"),
                Output("vtk-view", "triggerResetCamera"),
            ],
            [Input("dropdown-preset", "value"), Input("scale-factor", "value")],
        )
        def updatePresetName(name, scale_factor):
            points, polys, elevation, color_range = updateWarp(scale_factor)
            return [name, color_range, points, polys, elevation, random.random()]

        
        # Run the app
        
        # Run app in web-browser
        # webbrowser.open_new('http://127.0.0.1:2000/',new=1) # Open in Firefox
        command = "cmd /c start chrome http://127.0.0.1:2000/ --new-window"
        subprocess.Popen(command, shell=True)
        
        # Run the dash app
        app.run_server(port=2000) # Run the app
        
        
        return
    
    
    def __repr__(self):
        return "PlanetaryTerrain('{}')".format(self.demfile)
    
    def __str__(self):
        return str(pprint(vars(self)))
