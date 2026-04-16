# -*- coding: utf-8 -*-
"""
Created on Fri Apr 23 20:06:18 2021

@author: scott
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

# GEO processing
from owslib.wms import WebMapService
from osgeo import gdal, osr
import cartopy.crs as ccrs
import pyproj

# 3D plotting packages
import pyvista as pv
import vedo
import vtk
from vtk.util.numpy_support import vtk_to_numpy
#from ipywidgets import interact, Button
import trimesh
#import tetgen
import scipy
from scipy.spatial import Voronoi, voronoi_plot_2d
from scipy.spatial import Delaunay
import skimage.color
from PIL import Image

import pdb

# Module imports
from planetary.conversions_module import *


#%% Mesh Generation -----------------------------------------------------------

def mesh_from_obj(path,filename,meshtype,units=None):
    '''
    Generate a surface mesh from an .obj file.
    Creates a PyVista mesh object, Delaunay mesh object, or Trimesh object.

    Parameters
    ----------
    path : TYPE
        DESCRIPTION.
    filename : TYPE
        DESCRIPTION.
    meshtype  :  str
        Type of mesh to return.

    Returns
    -------
    mesh : TYPE
        DESCRIPTION.

    '''


    if meshtype in ['PyVista','Pyvista','PV','pv']:
        # Generate PyVista Mesh
        mesh = pv.read(str(path / filename))    # Pyvista mesh object
        if units in ['m','meters','metres']:
            # Scale points
            mesh.points *=1000

    elif meshtype in ['Trimesh','trimesh','tri']:
        # Generate Trimesh Mesh
        mesh = trimesh.load(path/filename) # Trimesh mesh object
        # Set scale
        if units is None:
            # Default units are km
            mesh.units = 'km'
        elif units in ['km','KM','Km']:
            mesh.units = 'km'
        elif units in ['m','meters','metres']:
            # Scale mesh to meters
            mesh.apply_scale(1000)
            mesh.units = 'm'
        # Note: Trimesh can be loaded from url using
        # >> trimesh.load_remote(url)
    elif meshtype in ['Delaunay']:
        pv_mesh = pv.read(path/filename)    # Pyvista mesh object
        # Generate Delaunay mesh object
        mesh = Delaunay(pv_mesh.points) # Delaunay mesh object (same structure as ast_mesh)


    return mesh

def save_mesh_to_obj(mesh,filename=None):
    '''
    Generate a trimesh version of the mesh and export to obj file.
    '''

    # Extract mesh points and faces
    points = mesh.points()
    faces = mesh.faces()

    # Generate trimesh object
    mesh2 = trimesh.Trimesh(vertices=points,faces=faces)

    # Specify filename
    if filename is None:
        fullfilename = data_dir + r'\test_mesh.obj'
    else:
        fullfilename = data_dir + r'\\' + filename

    # Export mesh as obj file
    mesh2.export(fullfilename)
    print('Mesh saved')

    return

def MakeFacesVectorized1(Nr,Nc):
    '''
    Generate list of faces for numpy grid
    (Nr,Nc) = shape of grid

    Note: This code snippet has been copied from a post by user Divakar on
    Stack Overflow.
    See: https://stackoverflow.com/questions/44934631/making-grid-triangular-mesh-quickly-with-numpy
    '''

    # Initialize array
    faces = np.empty((Nr-1,Nc-1,2,3),dtype=int)

    r = np.arange(Nr*Nc).reshape(Nr,Nc)

    faces[:,:, 0,0] = r[:-1,:-1]
    faces[:,:, 1,0] = r[:-1,1:]
    faces[:,:, 0,1] = r[:-1,1:]

    faces[:,:, 1,1] = r[1:,1:]
    faces[:,:, :,2] = r[1:,:-1,None]

    faces.shape =(-1,3)
    return faces

def save_obj_from_url(url,savepath,filename):
    '''
    Generate and save an .obj file from face and vertex data read from a url.

    Parameters
    ----------
    url : str
        URL containing face and vertex data.
    savedir : str
        Full pathname of the directory to save the file.
    filename : str
        Name of the file to save (ending in .obj).

    Returns
    -------
    None.

    '''

    print(url)
    print(savedir)
    print(filename)


    # Check if data directory exists
    if os.path.exists(savedir) == False:
        print("Warning! Directory does not exist.")
        # TODO: Add code here later to create the directory.


    if os.path.isfile(path+filename) == True:
        # File already exists.
        print("Warning! File already exists.")
    else:
        # No conflicting files.
        # Extract data from url and save to .obj file.
        print("Generating shapefile:", filename)
        urllib.request.urlretrieve(url, savedir+filename)

    return

# Mesh from DEM file ----------------------------------------------------------
def xyz_from_dem(filename):
    ''' Extract array of X,Y,Z coordinates from a raster file'''

    # Open the image using gdal
    ds = gdal.Open(filename)

    # Projection in WKT
    proj_wkt = ds.GetProjection()
    # e.g. 'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AXIS["Latitude",NORTH],AXIS["Longitude",EAST],AUTHORITY["EPSG","4326"]]'
    # Note: WGS84 = EPSG4326 = PlateCarree

    # Convert projection to osr SpatialReference object
    inproj = osr.SpatialReference()
    inproj.ImportFromWkt(proj_wkt)

    # Proj4 string
    inproj_proj4 = inproj.ExportToProj4()

    # Image data as array of pixels
    data = ds.ReadAsArray()
    # Remove nodata values

    nodataval = None
    nodataval = ds.GetRasterBand(1).GetNoDataValue() # No data value

    if nodataval is not None:
        data[data == nodataval] = np.nan

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

    return X, Y, data, inproj_proj4, proj_wkt


def mesh_from_dem(fullfilename, planet, meshtype, mesh_frame=None,units=None):
    '''Generate a pyvista or vtk mesh object from a numeric raster dem.'''


    # Extract data from raster file
    X, Y, data, inproj_proj4, proj_wkt = xyz_from_dem(fullfilename)
    elev = data.copy() # Elevation data [km]
    # Convert elev to m
    if units == 'km':
        elev = elev*1000.
    elif units is None:
        # Determine units from elev range
        pdb.set_trace()



    # Copy raster X, Y coordinates
    raster_X = X.copy()
    raster_Y = Y.copy()


    # Define parameters for transformation
    if planet in ['Luna','Moon']:
        Radius = 1737400.0 # Radius of planet (m)
    elif planet in ['Mars','mars']:
        # TODO: Ellipsoid a=3396190, b=3376200
        Radius = 3386190.0 # Radius of planet (m)
    elif planet.lower() == 'earth':
        # TODO: Set geoid
        Radius = 6378137.0 # Radius of planet (m)

    # Transform X,Y,Z data ---------------------------------------------------
    # 3 options for mesh_frame
    # 1. raster: reference frame is a flat map. Z data is offset by elevation.
    # 2. ENU. Reference frame is in local East-North-Up coordinates.
    # 3. ECEF. Reference frame is in globale ECEF coordinates

    if mesh_frame is None:
        mesh_frame = 'raster'

    if mesh_frame in ['raster']:
        # Case 1. Display DEM mesh. No transformation.
        # Coordinates use flat map, with Z data offset by elevation data.
        # Sub cases for projection
        if ('+proj=longlat' in inproj_proj4):
            # Lat/long (units deg)
            # Scale z data
            # if np.abs(X.max()) < 180.:
            zscale = 0.1
            Z = data*zscale

        else:
            # Map projection with units m or km

            # Check the units
            if '+units=m' in inproj_proj4:
                # Raster units in m. Convert to km

                # TODO: Add check to see units of dem elevation data
                Z = elev
                del data

                # Convert to km
                X = X/1000.
                Y = Y/1000.
                Z = Z/1000.
            else:
                # Raster units in km.
                pass


    elif mesh_frame in ['ECEF','ENU']:
        # Case 2. Transform projection to ECEF or ENU

        # Subcases

        if ('+proj=longlat' in inproj_proj4) or ('+datum=WGS84' in inproj_proj4):
            
            # Get central coordinates
            long0 = (X.min() + X.max())/2
            lat0 = (Y.min() + Y.max())/2
            
            # Convert lat/long coords to ECEF
            print('Converting Equatorial to ECEF')
            x_ecef,y_ecef,z_ecef = geodetic_to_ecef(Radius+elev.flatten(), # r
                                                    np.deg2rad(X.flatten()),    # Long
                                                    np.deg2rad(Y.flatten()),    # Lat
                                                    )
            X = x_ecef.reshape(X.shape)
            Y = y_ecef.reshape(X.shape)
            Z = z_ecef.reshape(X.shape)
            
            # Convert ECEF to ENU
            if mesh_frame == 'ENU':
                print('Converting ECEF to ENU')
                e,n,u = ecef_to_enu(X.flatten(),Y.flatten(),Z.flatten(),np.deg2rad(lat0),np.deg2rad(long0),r0=Radius)
                X = np.reshape(e,X.shape)
                Y = np.reshape(n,Y.shape)
                Z = np.reshape(u,Z.shape)
            
            # Convert to km
            X = X/1000.
            Y = Y/1000.
            Z = Z/1000.


        elif '+proj=stere' in inproj_proj4:
            # Convert stereographic to ECEF

            # Select method
            method = 2

            # Method 1. Using coordinate transforms ---------------------------
            if method == 1:

                # Convert X,Y coords to km
                X = X/1000.
                Y = Y/1000.

                # Convert X,Y to lat/long using polar_xy_to_lonlat function in
                # conversion module
                # FIXME: remove hardcoding of these values
                re = Radius/1000. # Radius of planet (km)
                true_scale_lat=90
                e = 0.
                hemisphere = -1
                lon, lat = polar_xy_to_lonlat(X.flatten(), Y.flatten(),
                                              true_scale_lat, re, e, hemisphere)

                # Convert lat,long to ecef
                x_ecef,y_ecef,z_ecef = geodetic_to_ecef(Radius+elev.flatten()*1000., # r
                                                        lon,    # Long
                                                        lat,    # Lat
                                                        )
                #x = -1744044.9517956264 to 1743419.3341953286
                pdb.set_trace()

            # B. Using GDALWARP (Faster) --------------------------------------
            elif method == 2:

                # TODO: Replace the output file with virtual
                # out_ds = gdal.Translate('/vsimem/in_memory_output.tif', in_ds)
                # see: https://gis.stackexchange.com/questions/316034/can-gdal-translate-return-an-object-instead-of-writing-a-file

                # Reproject raster to polar orthographic
                # Use GDAL warp to reproject raster to local orthographic
                print('Reprojecting Stereographic to Polar Orthographic')


                # Set newfilename of temporary tif
                infiledir = os.path.split(fullfilename)[0]
                infile = os.path.split(fullfilename)[1]
                outfile = 'temp_ortho_dem.tif'
                newfilename = str(Path(infiledir) / outfile)


                # Target Projection Proj4 string
                lat_0 = -90
                long_0 = 0.
                a = 1737400 # Semi-major axis
                b = 1737400 # Semi-minor axis
                t_srs = r'"+proj=ortho +lat_0={lat_0} +lon_0={long_0}'.format(lat_0=lat_0,long_0=long_0) \
                                + ' +x_0=0 +y_0=0 +a={a} +b={b} +units=m +no_defs "'.format(a=a,b=b)

                # "+proj=stere +lat_0=-90 +lon_0=0 +k=1 +x_0=0 +y_0=0 +a=1737400 +b=1737400 +units=m +no_defs "

                # Construct command prompt
                cmd = "gdalwarp -t_srs " + t_srs + \
                    " -of GTiff -r near -nosrcalpha -wo SOURCE_EXTRA=1000 -dstnodata -9999 " \
                    + '-ts ' + str(X.shape[0]) + ' ' + str(X.shape[1]) + ' ' \
                    +  infile + " " + outfile

                print('Reprojecting with gdalwarp\n')
                print(cmd)
                print('')

                # Note: set nodata value to -9999. this is to distinguish between
                # numeric dem raster that include points with elevation = 0.

                # Execute the command in console
                p = subprocess.Popen(cmd, shell=True, cwd=str(infiledir) ,stderr=subprocess.PIPE)
                # Wait until process is finished
                (output, err) = p.communicate()
                p_status = p.wait() # This makes the wait possible
                print(err) # Print any error to screen

                # Extract data from raster file
                X, Y, data, inproj_proj4, proj_wkt = xyz_from_dem(newfilename)
                orig_elev = elev.copy() # Copy of original elevation
                elev = data.copy() # Elevation data [km]

                # Convert elev to m
                if units == 'km':

                    # Check if units of elevation have changed
                    if np.nanmax(orig_elev)/np.nanmax(elev) > 100.:
                        # New projection is in km
                        elev = elev*1000.


                elif units is None:
                    # Determine units from elev range
                    pdb.set_trace()


                # TODO: Delete temp file
                Path(newfilename).unlink()


                # Calculate Z position from x,y
                print('Converting Local Orthographic to ENU')
                Z = elev.copy()

                Z += +np.sqrt(Radius**2 - X**2 - Y**2)
                # Note: This coordinate system is similar to ECEF, but upside down with
                # +Z pointing away from the south pole.

                # Convert to km
                X = X/1000.
                Y = Y/1000.
                Z = Z/1000.


                # Convert ENU to ECEF
                if mesh_frame == 'ECEF':

                    # TODO: Convert ENU to ECEF
                    pass

        elif ('+proj=eqc' in inproj_proj4) & ('+units=m' in inproj_proj4):
            # Convert Equidistant Cylindrical to ECEF


            print('Converting Equidistant Cylindrical to ECEF')
            # Use mathematical transfomation (pg 90 of Snyder)
            # See: https://proj.org/operations/projections/eqc.html
            # [Snyder, 1987] https://pubs.usgs.gov/pp/1395/report.pdf


            # Create dictionary of proj4 parameters
            proj_crs = pyproj.crs.CRS.from_string(inproj_proj4)
            proj4_dict = proj_crs.to_dict() # proj4 params as dictionary

            # Get reference latitude ( latitude of true scale)
            lat_ts=proj4_dict['lat_ts']
            lon_0=proj4_dict['lon_0']
            R = proj4_dict['R']

            # Convert x,y to lat/long (pg 90 of Snyder)
            # lambda = long = lamda0 + x/(R*cos(lat_ts))
            # phi = lat = y/R

            # Lat/long in radians
            lon = lon_0 + raster_X/(R*np.cos(np.deg2rad(lat_ts)))
            lat = raster_Y/R

            # Convert lat,long to ecef
            # (x,y,z) in ECEF
            x,y,z = geodetic_to_ecef(R+elev.flatten(), # r
                                    lon.flatten(),    # Long
                                    lat.flatten(),    # Lat
                                    )


            # Convert ECEF to ENU
            if mesh_frame == 'ENU':
                print('Converting ECEF to ENU')
                # Get the central latitude and longitude
                long0 = (np.nanmax(lon) + np.nanmin(lon))/2
                lat0 = (np.nanmax(lat) + np.nanmin(lat))/2


                # Convert ECEF to ENU
                x,y,z = ecef_to_enu(x,y,z,lat0,long0,r0=0)


            # Reshape
            X = x.reshape(X.shape)
            Y = y.reshape(X.shape)
            Z = z.reshape(X.shape)


            # Add elevation
            # Z += elev
            # Note: This coordinate system is similar to ECEF, but upside down with
            # +Z pointing away from the south pole.

            # Convert to km
            X = X/1000.
            Y = Y/1000.
            Z = Z/1000.
        
            

    # Create mesh -------------------------------------------------------------
    print('Creating Mesh')

    # Generate mesh
    if meshtype == 'vtkplotter':

        # Get the points as a 2D NumPy array (N by 3)
        points = np.c_[X.reshape(-1), Y.reshape(-1), Z.reshape(-1)]

        # # Create Delaunay triangulation to get faces
        # tri = Delaunay(points[:,:2])
        # faces = tri.simplices # List of faces

        # Generate faces for rectangular grid
        gridshape = Z.shape # (Nr,Nc)
        Nr = gridshape[0]
        Nc = gridshape[1]
        faces = MakeFacesVectorized1(Nr,Nc)

        # # Mesh using vtkplotter package
        # mesh = vtkplotter.mesh.Mesh([points,faces], c='Gray', alpha=1, computeNormals=False)

        # Mesh using newer vedo package
        mesh = vedo.mesh.Mesh([points,faces], c='Gray', alpha=1)
        # Add elevation as scalar (km)
        # mesh.addPointArray(elev.flatten()/1000., "Elevation")
        mesh.pointdata["Elevation"] = elev.flatten()/1000
        # # Add Raster X, Y coordinates as scalars
        # mesh.addPointArray(raster_X.flatten(), "raster_X")
        # mesh.addPointArray(raster_Y.flatten(), "raster_Y")

    elif meshtype == 'pyvista':

        # Structured Grid
        # x = X.flatten()
        # y = Y.flatten()
        # z = data.flatten()

        # https://docs.pyvista.org/examples/00-load/create-structured-surface.html


        # mesh = pv.StructuredGrid(X, Y, Z).triangulate()
        mesh = pv.StructuredGrid(X, Y, Z)
        mesh["Elevation"] = elev.ravel(order="F")/1000. # Elevation in km
        mesh.texture_map_to_plane(use_bounds=True, inplace=True)




        # # Create PolyData set of points
        # grid_poly = pv.PolyData(points)
        # mesh = pv.StructuredGrid() # Instantiate
        # # Set the points
        # mesh.points = grid_poly.points
        # # Set the dimension
        # mesh.dimensions = [data.shape[0],data.shape[1],1]


        # # Triangulated mesh
        # faces = np.hstack((np.full((len(faces), 1), 3), faces))
        # mesh = pv.PolyData(points,faces)


    # # Smooth mesh (works, but adds to runtime)
    # mesh.smoothLaplacian()

    # Lighting conditions
    # mesh.lighting(specular=0.0)

    return mesh





#%% Texture Mapping -----------------------------------------------------------

# Read in texture
def read_image_to_array(filename):
    '''Read a tif file and extract image data to numpy array.'''

    if '.tif' in filename:

        # Open the image using gdal
        ds = gdal.Open(filename)

        # Image data as array of pixels
        data = ds.ReadAsArray()

        if len(data.shape) == 2:
            # Data is 2D array
            img = data
            # Normalize values to range 0-255
            img_min = np.min(img)
            img_max = np.max(img)
            img = 255*(img-img_min)/(img_max-img_min)

            # Convert grayscale image to rgb
            img = skimage.color.gray2rgb(img)

            print('Warning! Numeric raster may not display.')

        else:
            # Data is 3D array

            img = data[:3, :, :].transpose((1, 2, 0))

            if img.shape[2] < 3:
                # Image only has 2 bands

                # Select first band only
                img = img[:,:,0]

                # Convert grayscale image to rgb
                img = skimage.color.gray2rgb(img)

    else:
        # raise ValueError(filename + ' is not a tif')


        import cv2
        img = cv2.imread(filename)


    return img

def texture_from_tif_pv(filename):
    ''' Generate a pyvista texture from an image file '''

    if '.tif' in filename:

        # Use GDAL to read image
        ds = gdal.Open(filename)
        tex = pv.numpy_to_texture(ds.ReadAsArray()[:3, :, :].transpose((1, 2, 0)))


    return tex


# Texture mapping
def add_texture_vtkplotter(mesh,filename):
    '''
    Add a georeferenced raster as texture to vtkplotter mesh.
    '''

    filenamePath = Path(filename) # Filename as path

    # Get mesh points
    points = mesh.points()
    # Convert points to m
    points = points*1000.

    # # Get raster X and Y coordinates
    # raster_X = mesh.getPointArray('raster_X')
    # raster_Y = mesh.getPointArray('raster_Y')

    # Open the image using gdal
    ds = gdal.Open(filename)

    # Geotransform
    gt = ds.GetGeoTransform()
    inv_gt = gdal.InvGeoTransform(gt) # Inverse transform


    # Convert to mesh vertices to pixel coords
    offsets = np.zeros(points[:,:2].shape) # Initialize
    for i in range(len(points)):
        offsets[i,:] = gdal.ApplyGeoTransform(inv_gt,points[i,0],points[i,1])
        # offsets[i,:] = gdal.ApplyGeoTransform(inv_gt,raster_X[i],raster_Y[i])
    # FIXME: find vectorized way to do this.

    # Get raster size

    # Convert to (u,v) texture coords (0 to 1)
    uv = offsets
    uv[:,0] = offsets[:,0]/ds.RasterXSize
    uv[:,1] = 1. - offsets[:,1]/ds.RasterYSize

    # Replace coords outside (0,1) with nan
    uv[np.amax(uv,axis=1) > 1.] = [np.nan,np.nan]
    uv[np.amin(uv,axis=1) < 0.] = [np.nan,np.nan]

    # Read image from filename and create vtk texture
    img = read_image_to_array(filename)
    tex = pv.numpy_to_texture(img)

    # Convert tiff to jpg
    if '.tif' in filename:
        print('Converting tif to bmp')
        im = Image.open(filename)
        im = im.convert("RGBA")
        # bmpfilename = filename[:-4] + '.png'
        bmpfilename = str(filenamePath.parent / 'temp_active_texture.png')
        im.save(bmpfilename)


    # # Apply texture from example textures (works)
    # mesh.texture('bricks', tcoords=uv, interpolate=True, repeat=False, edgeClamp=True)

    # Apply texture from bmp image
    mesh.texture(bmpfilename, tcoords=uv, interpolate=True, repeat=False, edgeClamp=False)

    # # Delete bmpfile # *** Can't do this while plotter is open
    # Path(bmpfilename).unlink()

    return mesh, uv

def add_t_coords_globe(mesh):
    '''
    Add texture coordinates for sphere.
    '''

    # Get mesh points
    points = mesh.points


    # uv mapping --------------------------------------------------------------
    # https://en.wikipedia.org/wiki/UV_mapping

    # Unit vector of points
    d1 = np.array(points)
    d1 = d1 / np.linalg.norm(d1, axis=-1)[:, np.newaxis]
    d1 = d1*-1 # Negative

    # Get x,y,z, compontents
    dx = d1[:,0]
    dy = d1[:,1]
    dz = d1[:,2]

    # Compute UV texture coordinates
    u = 0.5 + np.arctan2(dx,dz)/(2*np.pi)
    v = 0.5 - np.arcsin(dy)/(np.pi)

    # Convert to (u,v) texture coords (0 to 1)
    uv = np.zeros((len(points),2))
    uv[:,0] = u
    uv[:,1] = v

    # Fixing wrapping around join ---------------------------------------------
    # https://www.alexisgiard.com/icosahedron-sphere/
    # https://mft-dev.dk/uv-mapping-sphere/

    # Instantiate flags
    problem_face_flag = np.zeros(len(mesh.faces)) # Initialize flag of problem faces
    visited = np.zeros(len(mesh.points))*np.nan # Flag of visited vertices

    # Create copies of verties
    new_vertices = np.array(points.copy()) # Copy of points
    new_faces = mesh.faces.copy() # Copy of faces
    new_uv = uv.copy()

    # Loop through faces
    for i in range(len(mesh.faces)):

        # Get indices of face vertices (a,b,c)
        # (pyvista faces have 4 coordinates, skip the first entry)
        a_ind = mesh.faces[i,1]
        b_ind = mesh.faces[i,2]
        c_ind = mesh.faces[i,3]

        # Get texture coordinates (set 3rd coordinate to zero)
        a_vec = np.zeros(3);   a_vec[0:2] = uv[a_ind] # [u,v,0]
        b_vec = np.zeros(3);   b_vec[0:2] =uv[b_ind] # [u,v,0]
        c_vec = np.zeros(3);   c_vec[0:2] =uv[c_ind] # [u,v,0]

        # Get normal
        norm_vec = np.cross(b_vec - a_vec, c_vec - a_vec)

        # Find problem faces
        # If z component of normal is < 0
        if norm_vec[2] < 0:
            # Mark face as a problem
            problem_face_flag[i] = 1

            # Check each a,b,c vertex for probem vertices
            # (problem if u is close to 0, while the others are close to 1)

    # Loop through problem faces ----------------------------------------------
    problem_faces = np.where(problem_face_flag == 1.)[0]
    verticeIndex = len(points) - 1
    for i in problem_faces:

        # Get indices of face vertices (a,b,c)
        # (pyvista faces have 4 coordinates, skip the first entry)
        a_ind = new_faces[i,1]
        b_ind = new_faces[i,2]
        c_ind = new_faces[i,3]

        # Get verties of a,b,c
        a_vertex = new_vertices[a_ind] #
        b_vertex = new_vertices[b_ind] #
        c_vertex = new_vertices[c_ind] #


        # Check a vertex
        if new_uv[a_ind,0] < 0.25:

            # Check if it has been visited
            tempA = a_ind
            if np.isnan(visited[a_ind]):
                # Fix this vertex.
                new_uv = np.vstack((new_uv, new_uv[a_ind] + np.array([1,0]))) # Add copy of vertex
                # new_uv[a_ind,0] += 1 # Add 1 to u coordinate
                verticeIndex+= 1 # Increment index of new vertex
                new_vertices = np.vstack((new_vertices, a_vertex)) # Add copy of vertex
                visited[a_ind] = verticeIndex # Mark as fixed
                tempA = verticeIndex

            a_ind = tempA

        # Check b vertex
        if new_uv[b_ind,0] < 0.25:

            # Check if it has been visited
            tempB = b_ind
            if np.isnan(visited[b_ind]):
                # Fix this vertex.
                # new_uv[b_ind,0] += 1 # Add 1 to u coordinate
                new_uv = np.vstack((new_uv, new_uv[b_ind] + np.array([1,0]))) # Add copy of vertex
                verticeIndex+= 1 # Increment index of new vertex
                new_vertices = np.vstack((new_vertices, b_vertex)) # Add copy of vertex
                visited[b_ind] = verticeIndex # Mark as fixed
                tempB = verticeIndex

            b_ind = tempB

        # Check c vertex
        if new_uv[c_ind,0] < 0.25:

            # Check if it has been visited
            tempC = c_ind
            if np.isnan(visited[c_ind]):
                # Fix this vertex.
                # new_uv[c_ind,0] += 1 # Add 1 to u coordinate
                new_uv = np.vstack((new_uv, new_uv[c_ind] + np.array([1,0]))) # Add copy of vertex
                verticeIndex+= 1 # Increment index of new vertex
                new_vertices = np.vstack((new_vertices, c_vertex)) # Add copy of vertex
                visited[c_ind] = verticeIndex # Mark as fixed
                tempC = verticeIndex

            c_ind = tempC

        # Update face indices of triangles
        new_faces[i,1] = a_ind
        new_faces[i,2] = b_ind
        new_faces[i,3] = c_ind



    # mesh.t_coords = uv

    # Replace vertices, t_coords and faces of mesh
    mesh.points = new_vertices
    mesh.faces = new_faces
    mesh.t_coords = new_uv


    return mesh
