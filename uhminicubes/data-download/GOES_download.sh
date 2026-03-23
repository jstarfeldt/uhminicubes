#!/bin/bash

# Wall time limit
#SBATCH -t 4:00:00

# Number of CPU nodes
#SBATCH -n 1

# Number of CPU cores
#SBATCH -c 30

# Memory per CPU core
#SBATCH --mem-per-cpu=512

#export PATH=/home/jonstar/scratch/condaroot/miniforge3-24.11.3/bin:$PATH
#source activate heat
~/scratch/conda-pack-unpacker.sh -f ~/scratch/heat.tar.gz
if [ $? -ne 0 ]; then
    echo "[ERROR] Error unpackaging ~/scratch/foo.tar.gz"
    exit 1
fi

echo "First argument: $1"

cd /home/jonstar/ML_UH_datasets/uhminicubes/data-download
#/tmp/$USER/heat/bin/python GOES_download.py --city=$1 --n=105120 --startFile=0 --cpus=32
/tmp/$USER/heat/bin/python GOES_download.py --city=$1 --n=1 --startFile=3709 --cpus=32
