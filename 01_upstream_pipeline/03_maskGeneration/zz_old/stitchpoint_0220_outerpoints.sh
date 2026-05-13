#!/bin/bash
#SBATCH -J clustermap
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 32
#SBATCH -o stitch_%A.out
#SBATCH -e stitch_%A.err
#SBATCH --no-requeue

BASE_DIR=/gpfs/share/home/2301920002/lingyuan/20251010AD/1101/alldata/14mAD
PYTHON=/gpfs/share/home/2301920002/software/miniconda3/envs/clustermaptest/bin/python

$PYTHON new_stitch0220_outerpoints.py \
    -IXY 3072 \
    -ID  "$BASE_DIR" \
    -IO  "$BASE_DIR/04_stitch/orderlist" \
    -IS  "$BASE_DIR/03_segmentation/clustermap" \
    -OD  "$BASE_DIR/04_stitch" \
    -ITR "$BASE_DIR/04_stitch/stitchlinks/TileConfiguration.registered.txt" \
    -OC  "$BASE_DIR/04_stitch/cell_centerouter.csv" \
    -OR  "$BASE_DIR/04_stitch/remain_readsouter.csv" \
    -IT  "$BASE_DIR/04_stitch/stitchlinks/TileConfiguration.txt" \
    -SM  clustermap
