#!/bin/bash
#SBATCH -J clustermap
#SBATCH -p C64M256G
#SBATCH -N 1
#SBATCH -c 32
#SBATCH -o stitch_%A.out
#SBATCH -e stitch_%A.err
#SBATCH --no-requeue

BASE_DIR=/gpfs/share/home/2301920002/lingyuan/20251010AD/1101/alldata/14mAD

    # parser.add_argument('-IXY', '--input_xy', type=str, required=True,help='XY')
    # parser.add_argument('-ID', '--input_dir', type=str, required=True, help='the input_dir')
    # parser.add_argument('-IO', '--input_orderlist', type=str, required=True, help='input_orderlist')
    # parser.add_argument('-IS', '--input_segmentation', type=str, required=True, help='input_segmentation')
    # parser.add_argument('-OC', '--output_cell_center', type=str, required=True, help='output_cell_center')
    # parser.add_argument('-OD', '--output_dir', type=str, required=True, help='output_cell_center')
    # parser.add_argument('-OR', '--output_remain_reads', type=str, required=True, help='output_remain_reads')
    # parser.add_argument('-ITR', '--Tile_registered', type=str, required=True, help='Tile_registered')
    # parser.add_argument('-IT', '--Tile', type=str, required=True, help='TileConfiguration.txt')
    # parser.add_argument('-SM', '--seg_method', type=str, required=True, help='clustermap or watershed')



INPUT_XY=$1
INPUT_DIR=$2
INPUT_ORDERLIST=$3
INPUT_SEGMENTATION=$4
OUTPUT_CELL_CENTER=$5
OUTPUT_DIR=$6
OUTPUT_REMAIN_READS=$7
TILE_REGISTERED=$8
TILE=$9
SEG_METHOD=${10}


echo "[INFO] input_xy: $INPUT_XY"
echo "[INFO] input_dir: $INPUT_DIR"
echo "[INFO] input_orderlist: $INPUT_ORDERLIST"
echo "[INFO] input_segmentation: $INPUT_SEGMENTATION"
echo "[INFO] output_cell_center: $OUTPUT_CELL_CENTER"
echo "[INFO] output_dir: $OUTPUT_DIR"
echo "[INFO] output_remain_reads: $OUTPUT_REMAIN_READS"
echo "[INFO] Tile_registered: $TILE_REGISTERED"
echo "[INFO] Tile: $TILE"
echo "[INFO] seg_method: $SEG_METHOD"



python -u new_stitch0220_outerpoints.py \
    --input_xy "$INPUT_XY" \
    --input_dir "$INPUT_DIR" \
    --input_orderlist "$INPUT_ORDERLIST" \
    --input_segmentation "$INPUT_SEGMENTATION" \
    --output_cell_center "$OUTPUT_CELL_CENTER" \
    --output_dir "$OUTPUT_DIR" \
    --output_remain_reads "$OUTPUT_REMAIN_READS" \
    --Tile_registered "$TILE_REGISTERED" \
    --Tile "$TILE" \
    --seg_method "$SEG_METHOD"
