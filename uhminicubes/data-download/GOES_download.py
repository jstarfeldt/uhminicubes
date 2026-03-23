import ee
import pandas as pd
import numpy as np
from datetime import datetime
import glob
import multiprocessing
import argparse
import subprocess
import requests
import logging
from retry import retry

# Initialize Google Earth Engine project
ee.Initialize(project='ee-jonstar', opt_url='https://earthengine-highvolume.googleapis.com')


"""
Export coordinates for each urban area
KEY: [utm zone, boolean T/F for northern/southern hemisphere, utm x, utm y]
"""
export_coords = {
    'DMV':[18, True, 292000, 4372200],
    'NYC':[18, True, 561166, 4546228],
    'Phoenix':[12, True, 356592, 3758141],
    'Miami':[17, True, 503991, 2915332],
    'Chicago':[16, True, 386195, 4680677],
    'Denver':[13, True, 466349, 4442816],
    'Seattle':[10, True, 518589, 5311884],
    'San_Francisco':[10, True, 541523, 4206919],
    'Los_Angeles':[11, True, 346524, 3803779],
    'Atlanta':[16, True, 703143, 3787639],
    'Toronto':[17, True, 566749, 4867878],
    'Mexico_City':[14, True, 426632, 2177328],
    'Las_Vegas':[11, True, 618776, 4038562],
    'Salt_Lake_City':[12, True, 371135, 4538777],
    'Dallas':[14, True, 639754, 3678675],
    'Houston':[15, True, 232521, 3334892],
    'New_Orleans':[15, True, 723933, 3361201],
    'St_Louis':[15, True, 672050, 4323318],
    'Minneapolis':[15, True, 433510, 5031071],
    'Jacksonville':[17, True, 401561, 3376745],
    'Charlotte':[17, True, 472912, 3938294],
    'Philadelphia':[18, True, 445926, 4469797],
    'San_Diego':[11, True, 468102, 3666860],
    'San_Juan':[19, True, 732184, 2071833],
    'Montreal':[18, True, 564088, 5089380],
    'Guadalajara':[13, True, 621576, 2326245],
    'Monterrey':[14, True, 318956, 2885247],
    'Cancun':[16, True, 470776, 2369100],
    'Billings':[12, True, 655301, 5109344],
    'Guatemala_City':[15, True, 711929, 1659823],
    'San_Jose':[16, True, 772982, 1148166],
    'Havana':[17, True, 310663, 2566532],
    'Santo_Domingo':[19, True, 354586, 2108039],
    'Tegucigalpa':[16, True, 405549, 1616590],
    'Managua':[16, True, 524984, 1388932],
    'Panama_City':[17, True, 610881, 1043658],
    'Bogota':[18, True, 546442, 561743],
    'Lima':[18, False, 262348, 8709133],
    'Quito':[17, True, 733395, 16923],
    'Santiago':[19, False, 298834, 6329569],
    'Buenos_Aires':[21, False, 326030, 6204959],
    'Sao_Paulo':[23, False, 294104, 7446208],
    'Manaus':[20, False, 762422, 9716468],
    'Punta_Arenas':[19, False, 319805, 4162998],
    'La_Paz':[19, False, 548109, 8213756],
    'Montevideo':[21, False, 545458, 6223320],
    'Brasilia':[22, False, 783269, 8287283],
    'Caracas':[19, True, 687497, 1176029]
}


def scale_and_offset_GOES(image):
    """
    Applies scale and offset factors for GOES imagery.

    Args:
    image (ee.Image): GOES image to scale and offset

    Returns:
    brightness_temps (ee.Image): GOES image with bands in physical units
    """
    im = image.select(['CMI_C13', 'CMI_C14', 'CMI_C15', 'CMI_C16'])
    scales = image.toDictionary(['CMI_C13_scale', 'CMI_C14_scale', 'CMI_C15_scale', 'CMI_C16_scale']).toArray()
    offsets = image.toDictionary(['CMI_C13_offset', 'CMI_C14_offset', 'CMI_C15_offset', 'CMI_C16_offset']).toArray()
    scales_image = ee.Image.constant([scales.get([0]), scales.get([1]), scales.get([2]), scales.get([3])])
    offsets_image = ee.Image.constant([offsets.get([0]), offsets.get([1]), offsets.get([2]), offsets.get([3])])

    brightness_temps = im.multiply(scales_image).add(offsets_image)

    return brightness_temps


def process_GOES(image):
    """
    Preprocessing function for GOES images to scale
    and offset image bands and ensure the image
    timestamp is present.

    Args:
    image (ee.Image): GOES image to process

    Returns:
    GOES_image (ee.Image): Processed GOES image
    """
    # Scaling and offset
    GOES_image = scale_and_offset_GOES(image)

    ######################################
    # Timestamp portion

    # Function to get time from GOES image\
    def get_GOES_time(f):
        GOES_time = image.get('system:time_start')
        return f.set('timestamp', GOES_time)

    # Add timestamp back in
    GOES_image = get_GOES_time(GOES_image)

    return GOES_image


@retry(tries=10, delay=1, backoff=2)
def getResultGOES_new(city, city_export, dt, filename, verbose=False):
    """
    Handle the HTTP requests to download an image.

    Args:
        city (str): City name from valid list of cities.
        city_export (list): [UTM zone, Boolean T/F for Northern Hemisphere/Southern Hemisphere, UTM x for export, UTM y for export]
        dt (str): Date in format of 'YYYYmmddHHMM'.
        filename (str): Name of the file to save the export data in. '.tif' Should be included at the end of the file name.
        verbose (boolean): Whether or not to print out the filename when export is done.
    """
    # Sets up dates to be able to filter the GOES ImageCollection
    date_format = "%Y%m%d%H%M"
    date1 = datetime.strptime(dt, date_format)
    date2 = datetime.strptime(str(int(dt)+1), date_format)

    # Initialize GOES ImageCollection, process the images, and load in the corresponding timestamps
    # GOES-West
    if city in ['Seattle', 'San_Francisco', 'Los_Angeles', 'San_Diego', 'Phoenix', 'Las_Vegas', 'Salt_Lake_City']:
        if int(dt) < 202301040000:
            GOES = ee.ImageCollection("NOAA/GOES/17/MCMIPF").filterDate(date1, date2)
        else:
            GOES = ee.ImageCollection("NOAA/GOES/18/MCMIPF").filterDate(date1, date2)
    # GOES-East
    else:
        GOES = ee.ImageCollection("NOAA/GOES/16/MCMIPF").filterDate(date1, date2)
    processed = GOES.map(process_GOES)

    # Get the image from the filtered result
    # (should only be one in the result)
    image = processed.first()

    if city_export[1]:
        crs_prefix = '326' # Northern hemisphere
    else:
        crs_prefix = '327' # Southern hemisphere

    # Set up the region from which to export data
    crs = f'EPSG:{crs_prefix}{city_export[0]}'
    point = ee.Geometry.Point([city_export[2]+30*2999/2,city_export[3]-30*2999/2], crs)
    region = point.buffer(distance=44000, proj=crs).bounds(proj=crs)


    # Fetch the URL from which to download the image.
    url = image.getDownloadURL({
        'bands':['CMI_C13', 'CMI_C14', 'CMI_C15', 'CMI_C16'],
        'crs':crs,
        'region':region, 'scale':2000,
        'format': 'GEO_TIFF', 'filePerBand':False})

    # Handle downloading the actual pixels.
    r = requests.get(url, stream=True)
    if r.status_code != 200:
        #print('Unsuccessful request')
        raise r.raise_for_status()
    #print('request successful')

    with open(filename, 'wb') as out_file:
        out_file.write(r.content)
    if verbose:
        print("Done: ", filename)


if __name__ == '__main__':
    logging.basicConfig()

    parser = argparse.ArgumentParser(
                    prog='GOES_download',
                    description='Fast downloading for GOES images from GEE')
    parser.add_argument('--city', help='String of city from list of valid cities to make data for')
    parser.add_argument('--n', nargs='?', const=105120, help='Number of files to create')
    parser.add_argument('--startFile', nargs='?', const=0, help='File index to start from')
    parser.add_argument('--cpus', nargs='?', const=100, help='Number of CPU cores to run in parallel')
    args = parser.parse_args()

    # Pull points to make data for a specific city (look above for options)
    city = args.city
    city_export = export_coords[city]

    num = int(args.n)
    start = int(args.startFile)
    if num > 105120: # Largest number of files possible
        num = processed.size().getInfo()

    # Ensure there is a GOES directory made for the city and set it as the prefix to the filename
    subprocess.call(['mkdir', '-p', f'/home/jonstar/scratch/{city}_GOES'])
    file_prefix = f'/home/jonstar/scratch/{city}_GOES'

    # GOES-West
    if city in ['Seattle', 'San_Francisco', 'Los_Angeles', 'San_Diego', 'Phoenix', 'Las_Vegas', 'Salt_Lake_City']:
        g_times = pd.read_csv('/home/jonstar/urban_heat_dataset/GOES_West_times.csv')
    # GOES-East
    else:
        g_times = pd.read_csv('/home/jonstar/urban_heat_dataset/GOES_East_times.csv')

    # Finds indices of files that are not currently created
    time_strs = g_times.datetime[start:start+num]
    full_file_list = [f'{file_prefix}/GOES_image_{time_str}.tif' for time_str in time_strs] 
    current_file_list = sorted(glob.glob(f'{file_prefix}/*'))
    missing_indices = np.where([x not in current_file_list for x in full_file_list])[0]+start
    print('Length of missing indices:', len(missing_indices))

    # Sets up inputs for multiprocessing pool
    inputs = [[str(city), city_export, str(time_str), f'{file_prefix}/GOES_image_{time_str}.tif'] for time_str in time_strs[missing_indices]]

    # Run multiprocessing pool
    print('Starting multiprocessing')
    start = datetime.now()
    nCPUs = int(args.cpus)
    pool = multiprocessing.Pool(nCPUs)
    pool.starmap(getResultGOES_new, inputs)
    pool.close()
    pool.join()

    time_diff = datetime.now() - start
    print(f'Total time: {time_diff.total_seconds()} seconds')
