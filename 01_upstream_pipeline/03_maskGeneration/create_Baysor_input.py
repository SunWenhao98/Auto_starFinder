import pandas as pd
import numpy as np
import argparse
import os

def create_baysor_input_cylindrical(starmap_coords_path, cellpose_mask_path, output_csv_path, xy_scale, z_scale):
    """
    Creates Baysor input from STARmap data and a 2D Cellpose Mask.
    Assuming "Cylindrical" cells: Ignores Z-coordinate when assigning Cell IDs.
    """
    
    # 1. Read STARmap data
    print(f"Reading STARmap transcript data from: {starmap_coords_path}")
    transcripts_df = pd.read_csv(starmap_coords_path, header=0)
    
    required_cols = {'x', 'y', 'z', 'Gene'}
    if not required_cols.issubset(transcripts_df.columns):
        raise ValueError(f"Error: Input CSV must contain columns: {list(required_cols)}")

    # Extract coordinates
    pixel_x = transcripts_df['x'].values
    pixel_y = transcripts_df['y'].values
    # pixel_z = transcripts_df['z'].values # Cylindrical projection does not need Z for ID assignment

    # 2. Read 2D Cellpose Mask
    print(f"Reading 2D Cellpose mask: {cellpose_mask_path}")
    mask_image = np.load(cellpose_mask_path)
    
    # Check if mistakenly read a 3D mask, or handle squeeze
    if mask_image.ndim == 3:
        print("Warning: Loaded mask is 3D. Attempting to use max projection or squeeze.")
        mask_image = np.max(mask_image, axis=0)
    
    height, width = mask_image.shape
    print(f"2D Mask shape: H={height}, W={width}")

    # 3. Assign Cell ID (Cylindrical logic)
    print("Assigning cell IDs based on 2D projection (Cylindrical model)...")
    
    # Convert coordinates to integer indices
    idx_x = np.round(pixel_x).astype(int)
    idx_y = np.round(pixel_y).astype(int)

    # Boundary check
    valid_mask = (idx_x >= 0) & (idx_x < width) & (idx_y >= 0) & (idx_y < height)
    
    # Initialize all points' cell_id to 0 (background)
    cell_ids = np.zeros(len(transcripts_df), dtype=mask_image.dtype)
    
    # Only query points within image bounds
    # Note numpy indexing is usually [y, x]
    cell_ids[valid_mask] = mask_image[idx_y[valid_mask], idx_x[valid_mask]]

    num_assigned = (cell_ids > 0).sum()
    print(f"Assigned {num_assigned} transcripts ({num_assigned/len(transcripts_df):.2%}) to nuclei cylinders.")

    # 4. Generate output DataFrame (convert to microns)
    print("Converting pixel coordinates to microns for Baysor...")
    final_df = pd.DataFrame({
        'x': transcripts_df['x'] * xy_scale,
        'y': transcripts_df['y'] * xy_scale,
        'z': transcripts_df['z'] * z_scale,
        'gene': transcripts_df['Gene'],
        'cell_id': cell_ids
    })

    # 5. Save to CSV
    print(f"Saving final CSV to: {output_csv_path}")
    final_df.to_csv(output_csv_path, index=False)
    print("Preprocessing complete.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Create Baysor input using 2D Mask (Cylindrical projection).")
    parser.add_argument('--starmap_coords', required=True, help='STARmap CSV (pixel units).')
    parser.add_argument('--cellpose_mask', required=True, help='2D Cellpose NPY mask.')
    parser.add_argument('--output_csv', required=True, help='Output CSV path.')
    parser.add_argument('--xy_scale', type=float, required=True, help='Microns per pixel.')
    parser.add_argument('--z_scale', type=float, required=True, help='Microns per Z-step.')
    
    args = parser.parse_args()
    
    create_baysor_input_cylindrical(
        args.starmap_coords, 
        args.cellpose_mask, 
        args.output_csv, 
        args.xy_scale, 
        args.z_scale
    )