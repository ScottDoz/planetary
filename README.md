Modelling of planetary objects, bodies, surfaces.
-------------------------------------------------

[![Powered by Astropy](https://img.shields.io/badge/powered%20by-Astropy-orange.svg?style=flat)](https://astropy.org/)

This repo contains python tools to model planetary objects, bodies, and surfaces.

Example terrain plot of lunar south pole region.




Installation
------------

The geoprocessing packages used in this repo have many interdependencies. We recommend using conda-forge to download and manage dependencies.

#### Create a virtual environment using python 3.10
```
conda create -n planetary python=3.10 geopandas cartopy -c conda-forge
conda activate planetary
```

#### Install Core science packages
```
conda install -c conda-forge numpy scipy pandas matplotlib 
```

#### Install Geospatial packages
```
conda install gdal pyproj shapely geopandas cartopy owslib
```

#### Install astrodynamics packages
```
conda install -c conda-forge spiceypy astropy scikit-image
```

#### Install Visualization VTK packages
```
conda install vtk pyvista vedo tetgen trimesh
conda install -c conda-forge k3d
```



License
-------

This project is Copyright (c) ScottDoz and licensed under
the terms of the Other license. This package is based upon
the [Astropy package template](https://github.com/astropy/package-template) which is licensed under the BSD 3-clause license. See the licenses folder for more information.



