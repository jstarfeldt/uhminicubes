# Urban Heat MiniCubes: An AI-Ready Dataset for Urban Heat Research

## Overview
Urban heat is amplified by impermeable surfaces and heterogeneous built environments, yet street-level variability remains difficult to quantify because multi-sensor observations are rarely available in consistent, analysis-ready form at the necessary spatiotemporal scales. We present "Urban Heat MiniCubes", a publicly available, FAIR-oriented dataset designed for machine learning applications in urban heat research. The dataset provides harmonized $90\times90$ km gridded data cubes for 48 cities in the Western Hemisphere spanning 2022-2023, with variables reprojected and collocated to a common grid to reduce preprocessing (e.g., reprojection, resampling, and spatiotemporal alignment). Urban Heat MiniCubes includes two complementary modalities: (i) higher-spatial-resolution, lower-frequency observations from Landsat 8/9 (e.g., surface reflectances) and Sentinel-1 (e.g., synthetic aperture radar backscatter), and (ii) higher-temporal-frequency, coarser observations from GOES-R (e.g., longwave infrared brightness temperatures) and a microwave land surface temperature product.

## What you will find in this repository
* Code to download and process the data in the dataset
* Code to reproduce figures found in the preprint
* Yaml files to create the necessary conda environments

## Data Access
The dataset can be accessed on [NCAR's Geoscience Data Exchange (GDEX)](doi.org/10.5065/GNGZ-2510).

## Data sources and processing
Urban Heat MiniCubes is comprised of remotely sensed data from a number of satellites, including Landsat 8/9, Sentinel-1, and GOES-16/17/18. The code in this repository shows how to download data from these satellites from Google Earth Engine. These data are also publicly available online. Each file in the dataset is regridded to a $90\times90$ km grid in Universal Transverse Mercator (UTM) coordinates, named the "export grid", using nearest neighbor resampling. Processing for individual file modalities is listed below.

### High-spatial-resolution modality
* Spatial mosaicking of Landsat 8/9 data: When the export grid of a city was not covered by a single Landsat scene, a spatial mosaicking was performed, with the scene that overlapped most of the export grid being mosaicked on top.
* Spatio-temporal interpolation of Sentinel-1 data: Sentinel-1 images are filtered to any data within 6 days (half an orbital cycle) of Landsat 8/9 images. The resultant Sentinel-1 images are mosaicked, with the images closest in time to the Landsat 8/9 image mosaicked on top.
* The Landsat 8/9 cloud mask is provided as a bit string to improve readability.

### Low-spatial-resolution modality
* Microwave land surface temperature temporal interpolation: The microwave land surface temperature product is natively provided every 15 minutes in local solar time. These data are interpolated to the 10-minute temporal resolution of the GOES-R data by converting local solar time to UTC time as $\text{UTC time} = \text{Local Solar Time} - \left(\frac{\text{Longitude}}{360}\right) \times 24$.

## How are files stored in the dataset?
(a) Files are stratified by modality and sub-stratified by data files versus coordinate files. Data files contain physical variables. Coordinate files provide the corresponding latitude and longitude coordinates for the UTM grid in each city.

(b) Each filename follows a general structure. The structures of city data filenames are provided in blue and green, and the structure of latitude and longitude coordinate filenames is provided in orange.

<img width="1300" height="747" alt="directory_tree_presentation_MJM" src="https://github.com/user-attachments/assets/98d81c35-67d2-49ee-8c4a-b5754734fade" />
