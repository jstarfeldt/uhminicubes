import boto3
from botocore import UNSIGNED
from botocore.config import Config
import xarray as xr
import io
import numpy as np
from scipy import interpolate
import argparse
import subprocess
from datetime import datetime
import multiprocessing



def stringify_day(num):
    if len(str(num)) == 1:
        return f'00{num}'
    elif len(str(num)) == 2:
        return f'0{num}'
    else:
        return str(num)


def prefixify(num, year=2022):
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


def process_GOES_file(file_key, city):
    """
    Downloads a GOES cloud mask file from AWS, interpolates it to a given city's lresgrid,
    and saves the data as a netCDF file.

    Args:
    prefix (str): Directory path of the AWS bucket to download data from
    city (str): City str of the city to download data from
    """
    bucket_name = 'noaa-goes16'

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

    date = file_key.split('_s')[-1][:11]
    date_obj = datetime.strptime(date[:7], "%Y%j")
    fname = f'lresgrid_{city}_{date[:4]}{stringify_date(date_obj.month)}{stringify_date(date_obj.day)}{date[7:]}_mask.nc'

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
    response = s3.list_objects_v2(
        Bucket=bucket_name,
        Prefix=prefix,
        #MaxKeys=10
    )
    # Print the found object keys
    for obj in response.get('Contents', []):
        #print(obj['Key'])# Example of a specific netCDF file key from the bucket
        file_key = obj['Key']
        process_GOES_file(file_key, city)



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
    bucket_name = 'noaa-goes16'
    region = 'us-east-1' # The bucket is in us-east-1

    dates = list(map(lambda x: prefixify(x, year), range(1, 366)))

    # Sets up inputs for the multiprocessing pool
    inputs = [[date, city] for date in dates]

    # Run multiprocessing pool
    print('Starting multiprocessing')
    start = datetime.now()
    nCPUs = int(args.cpus)
    with multiprocessing.Pool(nCPUs, initializer=init_worker) as pool:
        pool.starmap(process_GOES_cloud_mask, inputs)

    time_diff = datetime.now() - start
    print(f'Total time: {time_diff.total_seconds()} seconds')
