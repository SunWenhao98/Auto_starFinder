import sys
import os
import argparse
import numpy as np
import pandas as pd
import tifffile as tif
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from skimage.morphology import dilation, disk
import warnings

# Suppress warnings for cleaner logs
warnings.filterwarnings("ignore")

# =============================================================================
# Helper: Mask Generation
# =============================================================================
def create_dilated_mask(shape, spots, radius, color_mode='random'):
    """
    Creates a colored mask layer from spot coordinates.
    
    Args:
        shape (tuple): (H, W) of the image.
        spots (pd.DataFrame): DataFrame with 'spot_location_1', 'spot_location_2', 'clustermap'.
        radius (int): Dilation radius.
        color_mode (str): 'random' for cell IDs, 'solid' for single color (e.g. process).
        
    Returns:
        np.ma.masked_array: The colored mask ready for imshow (background masked).
        ListedColormap: The colormap to use.
    """
    h, w = shape
    label_canvas = np.zeros((h, w), dtype=np.int32)
    
    if spots.empty:
        return None, None

    # Extract coordinates
    # spot_location_1 = X (Col), spot_location_2 = Y (Row)
    x = spots['spot_location_1'].values.astype(int)
    y = spots['spot_location_2'].values.astype(int)
    
    # Handle IDs based on mode
    if color_mode == 'random':
        # Cells: ID + 1 to reserve 0 for background
        ids = spots['clustermap'].values.astype(int) + 1
    else:
        # Process: Force all points to ID 1
        ids = np.ones(len(x), dtype=np.int32)

    # Boundary check
    mask_idx = (x >= 0) & (x < w) & (y >= 0) & (y < h)
    x, y, ids = x[mask_idx], y[mask_idx], ids[mask_idx]
    
    # Fill canvas
    label_canvas[y, x] = ids
    
    # Dilation
    if radius > 0:
        footprint = disk(radius)
        dilated = dilation(label_canvas, footprint=footprint)
    else:
        dilated = label_canvas
        
    # Mask background
    if np.max(dilated) == 0:
        return None, None
        
    masked_labels = np.ma.masked_where(dilated == 0, dilated)
    
    # Generate Colormap
    if color_mode == 'random':
        unique_cnt = int(np.max(dilated)) + 50
        rand_colors = np.random.rand(unique_cnt, 4)
        rand_colors[:, 3] = 1.0 # Alpha handled globally later
        rand_colors[0] = [0, 0, 0, 0] # Transparent background
        cmap = ListedColormap(rand_colors)
    elif color_mode == 'green':
        # Green for Process
        cmap = ListedColormap([[0, 1, 0, 1]]) 
    elif color_mode == 'red':
        # Red for Cells in merged view (optional, or stick to random)
        cmap = ListedColormap([[1, 0, 0, 1]])
        
    return masked_labels, cmap

# =============================================================================
# Core Visualization Function
# =============================================================================
def generate_combined_panel(dapi_img, spots_df, output_dir, radius, alpha):
    """
    Generates a single PNG with 3 Panels:
    1. Soma (Cells)
    2. Process (Neuropil)
    3. Merged
    """
    print(f"Generating 3-Panel QC Plot (Radius={radius})...")
    
    # --- 1. DAPI Processing ---
    if dapi_img.ndim == 3:
        dapi_max = np.max(dapi_img, axis=0)
    else:
        dapi_max = dapi_img
        
    # Normalize DAPI
    dapi_norm = dapi_max.astype(float)
    vmin, vmax = np.percentile(dapi_norm, 1), np.percentile(dapi_norm, 99)
    dapi_norm = np.clip((dapi_norm - vmin) / (vmax - vmin + 1e-8), 0, 1)
    
    h, w = dapi_norm.shape

    # --- 2. Data Splitting ---
    df_soma = spots_df[spots_df['clustermap'] >= 0]
    if 'is_noise' in spots_df.columns:
        df_process = spots_df[(spots_df['clustermap'] == -1) & (spots_df['is_noise'] == 0)]
        print(f"  Filtering Process using 'is_noise' column. Points found: {len(df_process)}")
    else:
        df_process = spots_df[spots_df['clustermap'] == -1]
        print(f"  Warning: 'is_noise' column missing. Using all unassigned points as Process. Points: {len(df_process)}")

    # --- 3. Plotting Setup ---
    # Create a figure with 3 subplots side-by-side
    fig, axes = plt.subplots(1, 3, figsize=(30, 10))
    plt.subplots_adjust(wspace=0.05, hspace=0)

    # --- Panel 1: Soma ---
    ax = axes[0]
    ax.imshow(dapi_norm, cmap='gray', interpolation='nearest')
    ax.set_title(f"Soma\n(Points: {len(df_soma['clustermap'])})", fontsize=18)
    ax.axis('off')
    
    mask_soma, cmap_soma = create_dilated_mask((h, w), df_soma, radius, color_mode='random')
    if mask_soma is not None:
        ax.imshow(mask_soma, cmap=cmap_soma, alpha=alpha, interpolation='nearest')

    # --- Panel 2: Process ---
    ax = axes[1]
    ax.imshow(dapi_norm, cmap='gray', interpolation='nearest')
    ax.set_title(f"Process\n(Points: {len(df_process)})", fontsize=18)
    ax.axis('off')
    
    mask_process, cmap_process = create_dilated_mask((h, w), df_process, radius, color_mode='green')
    if mask_process is not None:
        ax.imshow(mask_process, cmap=cmap_process, alpha=alpha, interpolation='nearest')

    # --- Panel 3: Merged ---
    ax = axes[2]
    ax.imshow(dapi_norm, cmap='gray', interpolation='nearest')
    ax.set_title("Merged (Soma + Process)", fontsize=18)
    ax.axis('off')

    # Layer 1: Process (Green)
    if mask_process is not None:
        ax.imshow(mask_process, cmap=cmap_process, alpha=alpha*0.8, interpolation='nearest')
    
    # Layer 2: Soma (Random Colors)
    if mask_soma is not None:
        ax.imshow(mask_soma, cmap=cmap_soma, alpha=alpha, interpolation='nearest')

    # --- 4. Saving ---
    save_filename = "vis_soma_process.png"
    save_path = os.path.join(output_dir, save_filename)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    print(f"Saved merged visualization to: {save_path}")

def command_args():
    parser = argparse.ArgumentParser(description="ClusterMap 3-Panel Visualization")
    parser.add_argument('--input_dapi', type=str, required=True)
    parser.add_argument('--input_csv', type=str, required=True)
    parser.add_argument('--output_dir', type=str, required=True)
    parser.add_argument('--qc_radius', type=int, default=5)
    parser.add_argument('--qc_alpha', type=float, default=0.5)
    return parser.parse_args()

if __name__ == '__main__':
    args = command_args()
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Loading DAPI: {args.input_dapi}")
    dapi = tif.imread(args.input_dapi)

    print(f"Loading CSV: {args.input_csv}")
    try:
        df = pd.read_csv(args.input_csv)
        df.columns = [c.lower() for c in df.columns]
    except Exception as e:
        print(f"Error loading CSV: {e}")
        sys.exit(1)

    # Check Columns
    required = ['spot_location_1', 'spot_location_2', 'clustermap']
    if not all(col in df.columns for col in required):
        print(f"Error: CSV missing required columns {required}")
        sys.exit(1)

    # Run Visualization
    generate_combined_panel(
        dapi_img=dapi,
        spots_df=df,
        output_dir=args.output_dir,
        radius=args.qc_radius,
        alpha=args.qc_alpha
    )
    
    print("Done.")