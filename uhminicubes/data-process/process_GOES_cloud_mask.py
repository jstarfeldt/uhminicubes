import boto3
from botocore import UNSIGNED
from botocore.config import Config
import xarray as xr
import io
import numpy as np
from scipy import interpolate
import argparse
import subprocess
from datetime import datetime, timedelta
import os
import multiprocessing



def stringify_day(num):
    """
    Turns a day-of-year integer (1-365) into
    its three-digit form.

    Args:
    num (int): Day-of-year integer to convert

    Returns:
    (str): Three-digit day-of-year as a string
    """
    if len(str(num)) == 1:
        return f'00{num}'
    elif len(str(num)) == 2:
        return f'0{num}'
    else:
        return str(num)


def prefixify(num, year=2022):
    """
    Creates a string with the AWS directory to grab
    GOES ACM files from. The directories are separated
    by the day of the year.

    Args:
    num (int): Day-of-year integer to grab data from
    year (int): Year to grab data from

    Returns:
    (str): Directory path to grab GOES ACM data from
    """
    return f'ABI-L2-ACMF/{year}/{stringify_day(num)}' # Example prefix for Full Disk imagery


def stringify_date(num):
    """
    Returns a day or month integer as a str, adding
    a zero in front if it is a single digit.

    Args:
    num (int): Integer to turn into a string

    Returns:
    (str): Two-digit day as a string
    """
    if num >= 0 and num < 10:
        return f'0{num}'
    else:
        return str(num)


def init_worker():
    global s3
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))


def process_GOES_file(file_key, bucket_name, city):
    """
    Downloads a GOES cloud mask file from AWS, interpolates it to a given city's lresgrid,
    and saves the data as a netCDF file.

    Args:
    file_key (str): Path of the file to download
    bucket_name (str): The AWS bucket to download data from
    city (str): City str of the city to download data from
    """
    # Test if file has already been created
    date = file_key.split('_s')[-1][:11]
    date_obj = datetime.strptime(date[:7], "%Y%j")
    fname = f'lresgrid_{city}_{date[:4]}{stringify_date(date_obj.month)}{stringify_date(date_obj.day)}{date[7:]}_mask.nc'
    if fname in existing_file_list:
        return

    # Download the file content into an in-memory byte buffer
    response = s3.get_object(Bucket=bucket_name, Key=file_key)
    file_bytes = response['Body'].read()

    # Open the netCDF data using xarray
    with xr.open_dataset(io.BytesIO(file_bytes)) as ds:

        # Example: Access a specific data variable (e.g., the 'CMI' reflectance/brightness temperature array)
        mask_data = ds['ACM'].values

    if city in ['KSEA', 'KSFO', 'KLAX', 'KSAN', 'KPHX', 'KLAS', 'KSLC']:
        ds_latlon = xr.open_dataset('/glade/derecho/scratch/jstarfeldt/uhminicubes_tmp/goes18_abi_full_disk_lat_lon.nc')
    else:
        ds_latlon = xr.open_dataset('/glade/derecho/scratch/jstarfeldt/uhminicubes_tmp/goes19_abi_full_disk_lat_lon.nc')

    dsG = xr.open_dataset(f'/gdex/data/d539393/low_resolution/grid/lresgrid_{city}_latlon.nc')
    latlon_pts_lresgrid = np.stack([dsG['longitude'], dsG['latitude']], axis=-1)

    min_lon = np.min(latlon_pts_lresgrid[:, :, 0])-0.1
    max_lon = np.max(latlon_pts_lresgrid[:, :, 0])+0.1
    min_lat = np.min(latlon_pts_lresgrid[:, :, 1])-0.1
    max_lat = np.max(latlon_pts_lresgrid[:, :, 1])+0.1

    mask = (
        (ds_latlon.latitude >= min_lat) &
        (ds_latlon.latitude <= max_lat) &
        (ds_latlon.longitude >= min_lon) &
        (ds_latlon.longitude <= max_lon)
    )
    ds_latlon = ds_latlon.where(
        mask,
        drop=True
    )

    latlon_pts_GOES = np.stack([ds_latlon['longitude'], ds_latlon['latitude']], axis=-1).reshape((-1, 2))

    # Find rows and columns containing at least one matching pixel
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)

    # Bounding indices
    row_idx = np.where(rows)[0]
    col_idx = np.where(cols)[0]

    # Crop the NumPy array
    values_cropped = mask_data[
        row_idx.min():row_idx.max() + 1,
        col_idx.min():col_idx.max() + 1
    ].flatten()

    values_cropped = values_cropped[~np.isnan(latlon_pts_GOES).any(axis=1)]
    latlon_pts_GOES = latlon_pts_GOES[~np.isnan(latlon_pts_GOES).any(axis=1)]

    GOES_cloud_mask = interpolate.griddata(latlon_pts_GOES, values_cropped, latlon_pts_lresgrid, method='nearest')

    ds_cloud = dsG.copy()
    ds_cloud['GOES_cloud_mask'] = (('y', 'x'), GOES_cloud_mask)
    del ds_cloud['latitude']
    del ds_cloud['longitude']

    ds_cloud['GOES_cloud_mask'].attrs['standard_name'] = 'quality_flag'
    ds_cloud['GOES_cloud_mask'].attrs['long_name'] = 'four level cloud mask'
    ds_cloud['GOES_cloud_mask'].attrs['flag_values'] = [0, 1, 2, 3]
    ds_cloud['GOES_cloud_mask'].attrs['flag_meaining'] = 'clear probably_clear probably_cloudy cloudy'
    ds_cloud['GOES_cloud_mask'].attrs['missing_value'] = np.nan
    ds_cloud['GOES_cloud_mask'].attrs['grid_mapping'] = 'spatial_ref'

    ds_cloud.to_netcdf(f'{processed_dir}/{city}/{fname}')


def process_GOES_cloud_mask(prefix, city):
    """
    Wrapper for downloading GOES cloud mask files.

    Args:
    prefix (str): Directory path of the AWS bucket to download data from
    city (str): City str of the city to download data from
    """
    if city in ['KSEA', 'KSFO', 'KLAX', 'KSAN', 'KPHX', 'KLAS', 'KSLC']:
        if prefix.split('/')[1] == '2023' and int(prefix.split('/')[-1]) >= 4:
            bucket_name = 'noaa-goes18'
        else:
            bucket_name = 'noaa-goes17'
    else:
        bucket_name = 'noaa-goes16'

    response = s3.list_objects_v2(
        Bucket=bucket_name,
        Prefix=prefix,
    )
    # Print the found object keys
    for obj in response.get('Contents', []):
        #print(obj['Key'])# Example of a specific netCDF file key from the bucket
        file_key = obj['Key']
        process_GOES_file(file_key, bucket_name, city)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(
                    prog='GOES_cloud_mask_process',
                    description='Fast downloading and processing for GOES cloud mask images')
    parser.add_argument('--city', help='String of city from list of valid cities to make data for')
    parser.add_argument('--year', help='Year to make data for')
    parser.add_argument('--cpus', nargs='?', const=32, help='Number of CPU cores to run in parallel')
    args = parser.parse_args()

    # Set projection to process data for a specific city
    # (look above for city options)
    city = args.city
    year = int(args.year)

    processed_dir = '/glade/derecho/scratch/jstarfeldt/uhminicubes/lresgrid/cloud_mask'
    subprocess.call(['mkdir', '-p', f'{processed_dir}/{city}'])

    # Create an S3 client with anonymous/unsigned configuration
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))

    # Create datetimes for full file list
    start_date = datetime(year, 1, 1, 0, 0)
    end_date = datetime(year+1, 1, 1, 0, 0)  # Excludes the next year's start
    datetimes = []
    current = start_date
    # Loop and increment by 10 minutes
    while current < end_date:
        datetimes.append(current)
        current += timedelta(minutes=10)

    # Finds files that have not yet been created
    full_file_list = [f'lresgrid_{city}_{year}{stringify_date(dt.month)}{stringify_date(dt.day)}{stringify_date(dt.hour)}{stringify_date(dt.minute)}_mask.nc' for dt in datetimes]
    existing_file_list = os.listdir(f'{processed_dir}/{city}')
    files_to_make = list(set(full_file_list) - set(existing_file_list))
    print('Files left to make:', len(files_to_make))

    # Find the Julian Day of each file that has not yet been created,
    # which is the input to the processing function because AWS groups
    # data by Julian Day
    days = [datetime.strptime(file.split('_')[2], '%Y%m%d%H%M').strftime('%j') for file in files_to_make]
    days_to_make = list(set(days))
   
    # Set up inputs for the multiprocessing pool
    date_roots = [prefixify(day, year) for day in days_to_make]
    inputs = [[date_root, city] for date_root in date_roots]

    # Run multiprocessing pool
    print('Starting multiprocessing')
    start = datetime.now()
    nCPUs = int(args.cpus)
    with multiprocessing.Pool(nCPUs, initializer=init_worker) as pool:
        pool.starmap(process_GOES_cloud_mask, inputs)

    time_diff = datetime.now() - start
    print(f'Total time: {time_diff.total_seconds()} seconds')
