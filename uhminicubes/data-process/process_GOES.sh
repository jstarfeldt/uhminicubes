#!/bin/bash

# Wall time limit
#SBATCH -t 00:15:00

# Number of CPU nodes
#SBATCH -n 1

# Number of CPU cores
#SBATCH -c 32

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
echo "Second argument: $2"
echo "Third argument: $3"
echo "Fourth argument: $4"

cd /home/jonstar/uhminicubes/uhminicubes/data-process
/tmp/$USER/heat/bin/python process_GOES.py --city=$1 --cpus=32 --section=$2 --startYear=$3 --useMicrowave=$4
