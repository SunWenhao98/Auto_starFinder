import argparse
import numpy as np
import tifffile
from cellpose import models, io, plot
import torch
import time
import os
import matplotlib.pyplot as plt
import pandas as pd
import cc3d
from importlib.metadata import version
from scipy import ndimage as ndi
from skimage.filters import threshold_otsu
from skimage.measure import regionprops
from skimage.morphology import disk, remove_small_objects
from skimage.segmentation import find_boundaries

CELLPOSE_MAJOR = int(version('cellpose').split('.')[0])

def build_model(use_gpu, model_type='nuclei'):
    if CELLPOSE_MAJOR >= 4:
        # Cellpose 4 always loads cpsam (model_type is ignored). Its bfloat16 default gave
        # run-to-run different masks and random get_masks_torch crashes on CPU; float32 is reproducible.
        return models.CellposeModel(gpu=use_gpu, use_bfloat16=False)
    return models.CellposeModel(gpu=use_gpu, model_type=model_type)

def dapi_scale(stack):
    mip = stack.max(axis=0)
    positive = mip[mip > 0]
    low, high = (float(v) for v in np.percentile(positive, (1, 95)))

    def scale(a):
        return np.clip((a.astype(np.float32) - low) / (high - low), 0, 1)

    return scale, float(threshold_otsu(scale(stack[:, ::8, ::8])))

def nuclei_3d(stack, labels):
    """3D extent of the 2D nuclei: per-layer Otsu gate intersected with the 2D labels (XT16MB recipe)."""
    scale, threshold = dapi_scale(stack)
    vol = np.zeros(stack.shape, dtype=np.uint16 if labels.max() < 65535 else np.uint32)
    for z in range(stack.shape[0]):
        filtered = ndi.median_filter(scale(stack[z]), size=5, mode='reflect')
        before = remove_small_objects(ndi.binary_fill_holes(filtered > threshold), min_size=10, connectivity=1)
        after = ndi.binary_fill_holes(ndi.binary_dilation(before, structure=disk(4)))
        vol[z] = np.where(after, labels, 0)
    return vol

def percennorm(img, miper=0, maper=100):
    img = np.array(img, dtype='float32')
    datamin = np.percentile(img, miper, method='midpoint')
    datamax = np.percentile(img, maper, method='midpoint')
    output = (img - datamin) / (datamax - datamin)
    output[output > 1] = 1
    output[output < 0] = 0
    return output

def calculate_stats(masks):
    if masks.max() == 0:
        return pd.DataFrame(columns=['label', 'area', 'centroid_y', 'centroid_x'])

    stats = cc3d.statistics(masks)
    areas = stats['voxel_counts'][1:]
    centroids = stats['centroids'][1:]
    
    df = pd.DataFrame({
        'label': np.arange(1, len(areas)+1),
        'area': areas,
        'centroid_y': centroids[:,0],
        'centroid_x': centroids[:,1]
        })
    unique_labels = np.unique(masks)
    unique_labels = unique_labels[unique_labels != 0]
    if len(unique_labels) == len(areas):
        df['label'] = unique_labels

    return df

def save_results(masks, img_norm, df, output_base, suffix):
    output_tif_path = output_base + f"{suffix}.tif"
    output_npy_path = output_base + f"{suffix}.npy"
    output_csv_path = output_base + f"{suffix}.csv"
    output_png_path = output_base + f"{suffix}_qc.png"

    # 1. Save TIF
    print(f"Saving TIF: {output_tif_path}")
    io.imsave(output_tif_path, masks)

    # 2. Save NPY
    print(f"Saving NPY: {output_npy_path}")
    np.save(output_npy_path, masks)

    # 3. Save CSV
    print(f"Saving CSV: {output_csv_path}")
    df.to_csv(output_csv_path, index=False)

    # 4. Save QC PNG
    print(f"Saving QC image: {output_png_path}")
    plt.ioff()
    fig = plt.figure(figsize=(12, 12))
    plt.imshow(img_norm, cmap='gray')

    # Draw outlines
    if masks.max() > 0:
        outlines = plot.utils.outlines_list(masks)
        for o in outlines:
            plt.plot(o[:,0], o[:,1], color='r', linewidth=1)

    plt.axis('off')
    plt.title(f"Count: {len(df)} cells ({suffix})")
    plt.savefig(output_png_path, dpi=150, bbox_inches='tight')
    plt.close(fig)

def segment_nuclei(model, img_norm, diameter):
    eval_kwargs = dict(diameter=None if diameter == 0 else diameter,
                       flow_threshold=0.4, cellprob_threshold=0.0, do_3D=False)
    if CELLPOSE_MAJOR < 4:
        eval_kwargs['channels'] = [0, 0]
    masks, flows, styles = model.eval(img_norm, **eval_kwargs)
    return masks

def segment_nuclei_3d(model, stack, diameter, anisotropy):
    eval_kwargs = dict(diameter=None if diameter == 0 else diameter, z_axis=0, do_3D=True,
                       anisotropy=anisotropy, flow_threshold=0.4, cellprob_threshold=0.0)
    if CELLPOSE_MAJOR < 4:
        eval_kwargs['channels'] = [0, 0]
    masks, flows, styles = model.eval(stack.astype(np.float32), **eval_kwargs)
    return np.asarray(masks)

def filter_nuclei_3d(stack, labels, min_voxels, junk_contrast, junk_solidity, shell=6):
    # drop specks, and ragged objects hardly brighter than a shell px ring around them
    counts = np.bincount(labels.ravel())
    small = np.nonzero((counts > 0) & (counts < min_voxels))[0]
    small = small[small > 0]
    big = counts >= min_voxels
    big[0] = False
    sized = np.where(big[labels], labels, 0)
    scale, _ = dapi_scale(stack)
    nz, height, width = labels.shape
    rows = [{'label': int(o), 'voxels': int(counts[o]), 'reason': 'small'} for o in small]
    for o, sl in enumerate(ndi.find_objects(sized), start=1):
        if sl is None:
            continue
        y0, y1 = max(0, sl[1].start - shell), min(height, sl[1].stop + shell)
        x0, x1 = max(0, sl[2].start - shell), min(width, sl[2].stop + shell)
        box = (sl[0], slice(y0, y1), slice(x0, x1))
        lab = sized[box]
        m = lab == o
        img = scale(stack[box])
        ring = ndi.binary_dilation(m, structure=np.ones((1, 3, 3), bool), iterations=shell) & (lab == 0)
        inside = float(img[m].mean())
        around = float(img[ring].mean()) if ring.any() else 0.0
        contrast = inside / around if around > 0 else np.inf
        foot = m.any(axis=0)
        solidity = float(regionprops(foot.astype(np.uint8))[0].solidity)
        zz, yy, xx = np.nonzero(m)
        rows.append({'label': o, 'voxels': int(counts[o]), 'centroid_z': zz.mean() + sl[0].start,
                     'centroid_y': yy.mean() + y0, 'centroid_x': xx.mean() + x0, 'area_2d': int(foot.sum()),
                     'contrast': contrast, 'solidity': solidity,
                     'reason': 'junk' if contrast < junk_contrast and solidity < junk_solidity else ''})
    columns = ['label', 'voxels', 'centroid_z', 'centroid_y', 'centroid_x', 'area_2d', 'contrast', 'solidity', 'reason']
    df = pd.DataFrame(rows, columns=columns).sort_values('label', ignore_index=True)
    keep = df.loc[df['reason'] == '', 'label'].to_numpy(dtype=np.int64)
    new_id = np.zeros(len(counts), dtype=np.uint16 if len(keep) < 65535 else np.uint32)
    new_id[keep] = np.arange(1, len(keep) + 1)
    df.insert(1, 'new_label', new_id[df['label'].to_numpy(dtype=np.int64)].astype(int))
    return new_id[sized], df

def save_results_3d(labels, stack, df, output_base):
    print(f"Saving 3D nuclei: {output_base}.tif")
    tifffile.imwrite(output_base + ".tif", labels, compression='zlib')
    df.to_csv(output_base + ".csv", index=False)
    lo, hi = np.percentile(stack.max(axis=0), (1, 99.8))
    layers = [int(stack.shape[0] * f) for f in (0.25, 0.5, 0.75)]
    plt.ioff()
    fig, axes = plt.subplots(1, 3, figsize=(24, 8))
    for ax, z in zip(axes, layers):
        rgb = np.dstack([np.clip((stack[z].astype(np.float32) - lo) / (hi - lo), 0, 1)] * 3)
        rgb[find_boundaries(labels[z], mode='inner')] = (1, 0.2, 0.2)
        ax.imshow(rgb)
        ax.set_title(f"layer {z + 1}")
        ax.axis('off')
    fig.suptitle(f"Count: {int((df['new_label'] > 0).sum())} nuclei (3D)")
    fig.savefig(output_base + "_qc.png", dpi=100, bbox_inches='tight')
    plt.close(fig)

def run_segmentation_3d(model, dapi_stack, output_base_3d, diameter, anisotropy, min_voxels, junk_contrast, junk_solidity):
    if dapi_stack.ndim != 3:
        raise ValueError("--seg_3d true needs a 3D DAPI stack")
    print(f"\nRunning 3D segmentation (Diameter={diameter if diameter > 0 else 'Auto'}, anisotropy={anisotropy})...")
    start_time = time.time()
    labels = segment_nuclei_3d(model, dapi_stack, diameter, anisotropy)
    print(f"3D segmentation finished in {time.time() - start_time:.2f} seconds: {labels.max()} objects")
    kept, df = filter_nuclei_3d(dapi_stack, labels, min_voxels, junk_contrast, junk_solidity)
    print(f"Kept {int((df['new_label'] > 0).sum())} nuclei; removed {int((df['reason'] == 'small').sum())} below {min_voxels} voxels "
          f"and {int((df['reason'] == 'junk').sum())} with contrast < {junk_contrast} and solidity < {junk_solidity}")
    save_results_3d(kept, dapi_stack, df, output_base_3d)

def run_segmentation_maxproj(dapi_path, output_base_path, diameter, no_gpu, threshold , model_type='nuclei', save_3d=False,
                             seg_3d=False, output_base_3d=None, anisotropy=1.0, min_voxels=10000,
                             junk_contrast=1.3, junk_solidity=0.8):
    # 1. Determine device
    use_gpu = not no_gpu and torch.cuda.is_available()
    device_name = "GPU" if use_gpu else "CPU"
    print(f"--- Starting 2D Max-Projection Segmentation on {device_name} ---")

    # 2. Read 3D DAPI stack
    print(f"Loading 3D DAPI stack: {dapi_path}")
    dapi_stack = io.imread(dapi_path) 

    print(f"Original shape: {dapi_stack.shape}")

    # 3. Max Projection to 2D
    if dapi_stack.ndim == 3:
        print("Performing Max Projection along Z-axis...")
        dapi_2d = np.max(dapi_stack, axis=0)
    elif dapi_stack.ndim == 2:
        print("Image is already 2D.")
        dapi_2d = dapi_stack
    else:
        raise ValueError(f"Unsupported image dimensions: {dapi_stack.ndim}")

    # 4. Normalize image
    print("Normalizing image...")
    dapi_2d_norm = percennorm(dapi_2d, 1, 99.8)
    # save normalized image for post check
    norm_output_path = output_base_path + "_norm.tif"
    print(f"Saving normalized image for post checking: {norm_output_path}")
    io.imsave(norm_output_path, dapi_2d_norm)

    # 5. Initialize Cellpose model
    print(f"Initializing Cellpose {CELLPOSE_MAJOR}.x model ('{model_type}' for Cellpose < 4, cpsam float32 otherwise)...")
    model = build_model(use_gpu, model_type)

    # 6. Run segmentation(RAW)
    print(f"Running 2D segmentation (Diameter={diameter if diameter>0 else 'Auto'})...")

    start_time = time.time()

    masks_raw = segment_nuclei(model, dapi_2d_norm, diameter)
    end_time = time.time()
    print(f"Segmentation finished in {end_time - start_time:.2f} seconds.")

    # --- PROCESS RAW DATA ---
    print("\nProcessing RAW data...")
    df_raw = calculate_stats(masks_raw)
    raw_total_area = df_raw['area'].sum()
    print(f"Raw detected cells: {len(df_raw)}")
    print(f"Overall area of raw dapi: {raw_total_area}")
    save_results(masks_raw, dapi_2d_norm, df_raw, output_base_path, suffix="_raw")

    # 3D labels of the raw nuclei, used by ClusterMap --binary_source cellpose
    if save_3d:
        if dapi_stack.ndim != 3:
            raise ValueError("--save_3d true needs a 3D DAPI stack")
        output_3d_path = output_base_path + "_raw_3d.tif"
        print(f"Saving 3D nuclei: {output_3d_path}")
        tifffile.imwrite(output_3d_path, nuclei_3d(dapi_stack, masks_raw), compression='zlib')


    # --- PROCESS FILTERED DATA ---
    print(f"\nProcessing FILTERED data (Threshold area >= {threshold})...")
    
    if len(df_raw) > 0:
        # Find labels that pass the threshold
        df_filtered = df_raw[df_raw['area'] >= threshold].copy()
        valid_labels = df_filtered['label'].values
        
        # Create a new mask with only valid labels
        masks_filtered = np.where(np.isin(masks_raw, valid_labels), masks_raw, 0)
        filtered_total_area = df_filtered['area'].sum()
        reduction_ratio = (1 - filtered_total_area / raw_total_area) * 100

        print(f"Overall area of filtered dapi: {filtered_total_area}")
        print(f"Area reduction ratio: {reduction_ratio:.2f}%")
        print(f"Filtered detected cells: {len(df_filtered)} (Removed {len(df_raw) - len(df_filtered)})")
    else:
        masks_filtered = np.zeros_like(masks_raw)
        df_filtered = pd.DataFrame(columns=['label', 'area', 'centroid_y', 'centroid_x'])
        print("No cells detected in raw data, skipping filtering logic.")

    save_results(masks_filtered, dapi_2d_norm, df_filtered, output_base_path, suffix="_filtered")

    if seg_3d:
        run_segmentation_3d(model, dapi_stack, output_base_3d, diameter, anisotropy, min_voxels, junk_contrast, junk_solidity)
    print("\n--- Process completed successfully! ---")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run 2D Cellpose on Max Projected DAPI.")
    parser.add_argument('--input', type=str, required=True, help='Path to the 3D DAPI TIFF stack.')
    parser.add_argument('--output_base', type=str, required=True, help="Base path for outputs.")
    parser.add_argument('--diameter', type=float, default=0, help='Estimated NUCLEI diameter. 0 for auto.')
    parser.add_argument('--no-gpu', action='store_true', help='Disable GPU usage.')
    parser.add_argument('--threshold', type=int, default=100, required=True, help="Threshold of valid nuclear area")
    parser.add_argument('--save_3d', choices=['true', 'false'], default='false', help="Also write <output_base>_raw_3d.tif (Z, Y, X labels)")
    parser.add_argument('--seg_3d', choices=['true', 'false'], default='false', help="Also run 3D Cellpose and write <output_base_3d>.tif")
    parser.add_argument('--output_base_3d', type=str, default=None, help="Base path for 3D outputs.")
    parser.add_argument('--anisotropy', type=float, default=1.0, help="z step / xy pixel size")
    parser.add_argument('--min_voxels', type=int, default=10000, help="Minimum 3D nucleus volume")
    parser.add_argument('--junk_contrast', type=float, default=1.3, help="Drop 3D objects below this contrast and --junk_solidity")
    parser.add_argument('--junk_solidity', type=float, default=0.8, help="Drop 3D objects below this solidity and --junk_contrast")
    args = parser.parse_args()
    if args.seg_3d == 'true' and not args.output_base_3d:
        parser.error("--seg_3d true needs --output_base_3d")

    run_segmentation_maxproj(args.input, args.output_base, args.diameter, args.no_gpu, args.threshold,
                             save_3d=args.save_3d == 'true', seg_3d=args.seg_3d == 'true',
                             output_base_3d=args.output_base_3d, anisotropy=args.anisotropy, min_voxels=args.min_voxels,
                             junk_contrast=args.junk_contrast, junk_solidity=args.junk_solidity)
