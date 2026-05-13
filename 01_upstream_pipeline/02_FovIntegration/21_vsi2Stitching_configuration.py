from pathlib import Path
import logging
import bioformats as bf
import javabridge as jb
import argparse
import pandas as pd
import numpy as np
import re
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ================= Configuration =================
# PIXEL_SIZE_UM = 0.1083333
# INVERT_Y = False 
# ===============================================

def extract_index(f, pattern):
    match = re.search(pattern, f.name)
    return int(match.group(1)) if match else float('inf')

def get_vsi_position(path: str):
    xml_data = bf.get_omexml_metadata(path)
    omexml = bf.OMEXML(xml_data)
    pixels = omexml.image(0).Pixels
    phys_x = pixels.plane(0).PositionX
    phys_y = pixels.plane(0).PositionY
    return phys_x, phys_y

def main():
    parser = argparse.ArgumentParser(description="VSI to TileConfiguration (ID from filename)")
    parser.add_argument('--input_dir', '-i', type=Path, required=False, 
                        default=Path("/mnt/swh_c2/ZXM_DATA_1_disk/250615-MB-seqF4-2"),
                        help='The path to the input file.')
    parser.add_argument('--output_dir','-o', type=Path, required=False, 
                        default=Path("/media/zenglab/result/swh/07_Olympus_TEST/01_OlympusTest/01_data/round002"),
                        help='The path to the output directory.')
    parser.add_argument('--match_string', '-m', type=str, required=False, 
                        default="C1", 
                        help='The string to match the input file.')
    
    parser.add_argument('--pixel_size_um', '-p', type=float, required=False, default=0.1083333,
                        help='The pixel size in microns.')
    parser.add_argument('--image_xy', '-xy', type=int, required=False, default=2304,
                        help='The image size in pixels in x and y direction.')
    parser.add_argument('--overlap_ratio', '-r', type=float, required=False, default=0.1,
                        help='The overlap ratio between adjacent tiles.')
    parser.add_argument('--invert_y', '-iy', action='store_true', required=False, default=False,
                        help='Whether to invert the y-axis.')
    
    args = parser.parse_args()

    input_dir = args.input_dir
    output_dir = args.output_dir
    match_string = args.match_string

    PIXEL_SIZE_UM = args.pixel_size_um
    image_xy = args.image_xy
    non_overlap_len = image_xy * (1 - args.overlap_ratio)
    INVERT_Y = args.invert_y 
    
    output_dir.mkdir(parents=True, exist_ok=True)

    files = list(input_dir.glob(f"*{match_string}*.vsi"))
    pattern = fr'{re.escape(match_string)}-(\d+)'
    files = sorted(files, key=lambda f: extract_index(f, pattern))
    logging.info(f"File scan complete. Found {len(files)} files.")

    jb.start_vm(class_path=bf.JARS, run_headless=True, args=['-Dlog4j2.simplelogStatusLogger.level=off'])
    jb.static_call("loci/common/DebugTools", "enableLogging", "(Ljava/lang/String;)Z", "ERROR")
    print("Java VM started successfully")
    try:
        t0 = time.time()
        tiles_data = []
        for idx, f in enumerate(files):
            print(f"\rProcessing: [{idx+1}/{len(files)}] {f.name}", end='', flush=True)
            
            try:
                real_id = extract_index(f, pattern)
                phys_x, phys_y = get_vsi_position(str(f))
                tiles_data.append({
                    'original_name': f.name,
                    'real_id': int(real_id),
                    'phys_x': phys_x,
                    'phys_y': phys_y
                })
                
            except Exception as e:
                logging.error(f"\nFailed to read file {f.name}: {e}")

        print("")

        if not tiles_data:
            logging.error("No valid data extracted.")
            return

        df = pd.DataFrame(tiles_data)
        
        min_x = df['phys_x'].min()
        min_y = df['phys_y'].min()
        max_y = df['phys_y'].max()

        df['pos_x_px'] = (df['phys_x'] - min_x) / PIXEL_SIZE_UM
        if INVERT_Y:
            df['pos_y_px'] = (max_y - df['phys_y']) / PIXEL_SIZE_UM
        else:
            df['pos_y_px'] = (df['phys_y'] - min_y) / PIXEL_SIZE_UM

        output_config_path = output_dir / "TileConfiguration.txt"

        with open(output_config_path, 'w') as f:
            f.write("# Define the number of dimensions we are working on\n")
            f.write("dim = 3\n\n")
            f.write("# Define the image coordinates\n")
            
            for _, row in df.iterrows():
                fname = f"Position{int(row['real_id']):03d}.tif"
                
                x = row['pos_x_px']
                y = row['pos_y_px']
                f.write(f"{fname}; ; ({x:.2f}, {y:.2f}, 0.0)\n")

        logging.info(f"Generation complete: {output_config_path}")

    # TODO: 读取每个tile的位置信息，并绘图，将每个tile的位置绘制出来, 每个Tile都用 小正方形表示，左上角坐标呈现刚刚提取的位置信息。


    except Exception as e:
        logging.error(f"Global error occurred: {e}", exc_info=True)
    finally:
        jb.kill_vm()

if __name__ == "__main__":
    main()
