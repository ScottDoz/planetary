# -*- coding: utf-8 -*-
"""
Created on Fri Nov 27 14:45:25 2020

@author: scott

Test scripts for the planetary_bodies module.
"""

import numpy as np
import pandas as pd
import os
from os import path
import timeit



# Module imports
from planetary.Surfaces import *
from planetary.utils import get_data_home


# Set data directory
DATA_DIR = get_data_home()

#%% ###########################################################################
#                          UNIT TESTS
# #############################################################################

# The following main functions are set up to test the planetary_bodies.py module.
# They are defined as main functions to allow return of all variables to workspace.
# The tests are defined here to allow fast writing of test functions.

# To disable any of the tests, change the name to anything other than "__main__"
# (e.g. change name to "__main2__").



# #############################################################################

#%%
def test_lunar_south_pole():
    
    # Lunar South Pole Region
    
    # Load details from config
    configfile = DATA_DIR/'Planets'/'Luna'/'Regions'/'Lunar_South_Pole'/'config.xlsx' # Config file
    
    # Instantiate
    LunaRegion = PlanetaryRegion(configfile) # Instantiate
    
    # Raster processing -------------------------------------------------------
    # Generate rasters from wms
    LunaRegion.generate_wms_rasters() # Generate requested wms-derived rasters
    LunaRegion.generate_dem_products('luna_wac_dtm_numeric.tif') # Process dem products
    
    # Rasterize a shapefile
    LunaRegion.rasterize_shapefile('LOLA_81S_SP_PSR_STEREOGRAPHIC_10KM2_20170227.shp', 
                                    'LOLA_81S_SP_PSR_STEREOGRAPHIC_10KM2_20170227.tif', 
                                    'luna_wac_dtm_numeric.tif',
                                    )
    
    # TODO: Create proximity map
    
    
    # Generate a custom constraint map
    # TODO: Add argument for outfile name
    LunaRegion.generate_constraint_map('luna_wac_dtm_numeric.tif', # DEM file
                                       slope_const = [0,15], # Slope constraints (deg)
                                       )
    
    # LunaRegion.resample_raster('LOLA_81S_SP_PSR_STEREOGRAPHIC_10KM2_20170227.shp',
    #                         'LOLA_81S_SP_PSR_STEREOGRAPHIC_10KM2_20170227.tif',size=(1080,1080))
    
    
    # LunaRegion.add_craters() # Add craters
    
    # # Get details of a shapefile
    # df = LunaRegion.get_shapes(LunaRegion.shapes[0])
    
    # TODO: Method to segment a planetary terrain by geological units defined in shapefiles
    # see: https://github.com/pyvista/pyvista-support/issues/338
    
    # Plot layers
    LunaRegion.plot_raster_cartopy('luna_wilhelms_geologic_i1162.tif', cmap='jet', showgrid=True, alpha=1.)
    
    
    # Terrain Model -----------------------------------------------------------
    
    # Add a terrain model from DEM
    LunaRegion.SetPlanetaryTerrain(LunaRegion.rasters[0],
                                   meshtype='pyvista',mesh_frame='ENU',units='km')
    
    # Plot
    # LunaRegion.terrain.plot_vtk(export_html=True)
    LunaRegion.terrain.plot_pv()
    
    return LunaRegion

#%% Atlas Crater

def test_atlas_crater():
    
    # Load details from config
    # configfile = DATA_DIR/'Planets'/'Luna'/'Regions'/'Atlas'/'config.xlsx' # Config file
    configfile = DATA_DIR/'Planets'/'Luna'/'Regions'/'Atlas'/'config.json' # Config file
    
    # Instantiate
    Region = PlanetaryRegion(configfile) # Instantiate
    
    # Raster processing -------------------------------------------------------
    # Generate rasters from wms
    Region.generate_wms_rasters() # Generate requested wms-derived rasters
    Region.generate_dem_products('luna_wac_dtm_numeric.tif') # Process dem products
    
    # # Rasterize a shapefile
    # Region.rasterize_shapefile('GeoUnits.shp', 
    #                            'GeoUnits.tif', 
    #                            'luna_wac_dtm_numeric.tif',
    #                            )
    
    # TODO: Create proximity map
    
    
    # Generate a custom constraint map
    # TODO: Add argument for outfile name
    Region.generate_constraint_map('luna_wac_dtm_numeric.tif', # DEM file
                                   slope_file = 'luna_wac_dtm_numeric_slope.tif', slope_const = [0,10], # Slope constraints (deg)
                                   output='binary'
                                   )
    
    # Region.add_craters() # Add craters
    
    # # Get details of a shapefile
    # df = Region.get_shapes(Region.shapes[0])
    
    # TODO: Method to segment a planetary terrain by geological units defined in shapefiles
    # see: https://github.com/pyvista/pyvista-support/issues/338
    
    # Plot layers
    # Region.plot_raster_cartopy(Region.rasters[2], cmap='jet', showgrid=True, alpha=1.)
    # Region.plot_raster_cartopy('luna_wilhelms_geologic_i0703.tif', showgrid=True, alpha=1.)
    
    # Region.plot_raster_cartopy(Region.rasters[2],shape_name='GeoUnits.shp', cmap='jet', showgrid=True, alpha=1.,alpha_shp=0.3)
    # Region.plot_raster_cartopy('custom_constraints.tif', showgrid=True, alpha=1.)
    
    # # Plot Rasters
    # Region.plot_raster_cartopy('luna_wac_global.tif', cmap='jet', showgrid=True, alpha=1.) 
    # Region.plot_raster_cartopy('luna_wilhelms_geologic_i0703.tif', showgrid=True, alpha=1.)
    # Region.plot_raster_cartopy(Region.rasters[2],shape_name='GeoUnits.shp', cmap='jet', showgrid=True, alpha=1.,alpha_shp=0.3)
    
    # # Plot DEM values
    # Region.plot_raster_cartopy('luna_wac_dtm_numeric.tif', cmap='jet', showgrid=True, alpha=1.)
    # Region.plot_raster_cartopy('luna_wac_dtm_numeric_slope.tif', cmap='jet', showgrid=True, alpha=1.)
    # Region.plot_raster_cartopy('luna_wac_dtm_numeric_roughness.tif', cmap='jet', showgrid=True, alpha=1.)
    
    from matplotlib.colors import ListedColormap
    Region.plot_raster_cartopy('custom_constraints.tif', cmap=ListedColormap(['black', 'white']), showgrid=True, alpha=1.)
    
    # Terrain Model -----------------------------------------------------------
    
    # # Add a terrain model from DEM
    # Region.SetPlanetaryTerrain(Region.rasters[0],
    #                                meshtype='pyvista',mesh_frame='ENU',units='m')
    
    # Plot
    # # LunaRegion.terrain.plot_vtk(export_html=True)
    # Region.terrain.plot_pv()
    
    
    return Region


#%% PlanetaryRegion and PlanetaryTerrain --------------------------------------

if __name__ == '__main__':
    '''
    Lunar South Pole Region
    
    This script demonstrates the raster generation capabilities of the 
    PlanetaryRegion class.
    '''
    # # Lunar South Pole Region
    # configfile = DATA_DIR/'Planets'/'Luna'/'Regions'/'Lunar_South_Pole'/'config.xlsx' # Config file
    # Region = test_lunar_south_pole()
    
    # Atlas Region
    # configfile = DATA_DIR/'Planets'/'Luna'/'Regions'/'Atlas'/'config.xlsx' # Config file
    configfile = DATA_DIR/'Planets'/'Luna'/'Regions'/'Atlas'/'config.json' # Config file
    Region = test_atlas_crater()
    


if __name__ == '__main__2':
    '''
    Test PlanetaryRegion classes.
    Generate a model of a defined region on a planetary surface.
    '''

    # Define and Generate Lunar PlanetaryRegion -------------------------------
    
    # # Global lunar region
    # configfile = DATA_DIR/'Planets'/'Luna'/'Regions'/'Global'/'config.xlsx' # Config file
    # LunaGlobe = PlanetaryRegion(configfile) # Instantiate
    # LunaGlobe.generate_wms_rasters() # Generate requested wms-derived rasters
    # LunaGlobe.generate_dem_products('luna_wac_dtm_numeric.tif') # Process dem products
    # LunaGlobe.SetPlanetaryTerrain(LunaGlobe.rasters[0],meshtype='vtkplotter',mesh_frame='ECEF')
    
    
    # # Mars Jezero Crater
    # configfile = DATA_DIR/'Planets'/'Mars'/'Regions'/'Jezero'/'config.xlsx' # Config file
    # Jezero = PlanetaryRegion(configfile) # Instantiate
    # Jezero.generate_wms_rasters() # Generate requested wms-derived rasters
    # # Resample hirise dem
    # Jezero.resample_raster('JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif',
    #                         'JEZ_DTM_resample.tif',size=(1080,1080))
    # # # Jezero.generate_dem_products('mars_mola_dem_numeric.tif') # Process dem products
    # # Jezero.SetPlanetaryTerrain('JEZ_DTM_resample.tif',meshtype='pyvista',mesh_frame='ENU')
    # Jezero.SetPlanetaryTerrain('JEZ_DTM_resample.tif',meshtype='vtkplotter',mesh_frame='ENU')
    

if __name__ == '__main__2':
    '''
    Earth Region
    
    This script demonstrates the raster generation capabilities of the 
    PlanetaryRegion class.
    '''
    # Load details from config
    # configfile = DATA_DIR/'Planets'/'Earth'/'Regions'/'KahibahOval'/'config.xlsx' # Config file
    configfile = DATA_DIR/'Planets'/'Earth'/'Regions'/'KahibahOval'/'config.json' # Config file
    
    Region = PlanetaryRegion(configfile) # Instantiate
    
    # Generate rasters from wms
    Region.generate_wms_rasters() # Generate requested wms-derived rasters
    # Region.generate_dem_products('dtm_numeric.tif') # Process dem products

    # # Get details of a shapefile
    # df = LunaRegion.get_shapes(LunaRegion.shapes[0])
    
    # TODO: Method to segment a planetary terrain by geological units defined in shapefiles
    # see: https://github.com/pyvista/pyvista-support/issues/338
    
    # Plot dem
    Region.plot
    
    
    # Add a terrain model from DEM
    Region.SetPlanetaryTerrain(Region.rasters[1],
                                    meshtype='pyvista',mesh_frame='ENU',units='m')
    # terrain = Region.terrain
    # terrain.plot_vtk() # Plot
     
    

#%% PlanetaryRegion and PlanetaryTerrain --------------------------------------

if __name__ == '__main__2':
    '''
    Test PlanetaryTerrain classes.
    Generate a model of a defined region on a planetary surface.
    '''
    
    # Note: Useful reference for Mars DEMs
    # https://areobrowser.com/#/id=JEZ_hirise_soc_006
    
    
    # Define and Generate Lunar PlanetaryRegion and PlanetaryTerrain ----------
    
    # # Global lunar region
    # configfile = DATA_DIR/'Planets'/'Luna'/'Regions'/'Global'/'config.xlsx' # Config file
    # LunaGlobe = PlanetaryRegion(configfile) # Instantiate
    # LunaGlobe.generate_wms_rasters() # Generate requested wms-derived rasters
    # LunaGlobe.generate_dem_products('luna_wac_dtm_numeric.tif') # Process dem products
    # LunaGlobe.SetPlanetaryTerrain(LunaGlobe.rasters[0],meshtype='vtkplotter',mesh_frame='ECEF')
    
    # Lunar South Pole Region
    configfile = DATA_DIR/'Planets'/'Luna'/'Regions'/'Lunar_South_Pole'/'config.xlsx' # Config file
    LunaRegion = PlanetaryRegion(configfile) # Instantiate
    # LunaRegion.add_craters() # Add craters
    # # Pyvista/ENU Mesh
    # LunaRegion.SetPlanetaryTerrain(LunaRegion.rasters[0],meshtype='pyvista',mesh_frame='ENU',units='km')
    # VTK/ENU Mesh
    LunaRegion.SetPlanetaryTerrain(LunaRegion.rasters[0],meshtype='vtkplotter',mesh_frame='ENU',units='km')
    # LunaRegion.SetPlanetaryTerrain(LunaRegion.rasters[0],meshtype='vtkplotter',mesh_frame='raster',units='km')
    # Select a texture to plot
    # texfile = LunaRegion.get_raster_filename(LunaRegion.rasters[1]) # DEM
    # texfile = LunaRegion.get_raster_filename(LunaRegion.rasters[2]) # WAC 
    # texfile = LunaRegion.get_raster_filename(LunaRegion.rasters[3]) # Ilumnination 
    texfile = LunaRegion.get_raster_filename(LunaRegion.rasters[11]) # Geological Map
    
    
    # Plot the Terrain models -------------------------------------------------
    
    # # Plot using vtk
    # LunaRegion.terrain.plot_vtk() # Plot vtk
    
    # # Convert mesh to pyvista
    # LunaRegion.terrain.convert_meshtype('pyvista') # Convert the mesh to pyvista
    
    # # Plot using pyvista
    # LunaRegion.terrain.plot_pv()
    
    