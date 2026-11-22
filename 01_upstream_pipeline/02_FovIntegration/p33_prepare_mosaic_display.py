#!/usr/bin/env python3
"""Package aligned 2D planes as pyramidal OME-TIFFs and PNG previews."""

import argparse
from contextlib import ExitStack, contextmanager
import json
import math
from pathlib import Path
import re

import numpy as np
from PIL import Image
from scipy.ndimage import white_tophat
import tifffile
import zarr


TILE_SIZE = 512
PNG_MAX_EDGE_PX = 2048


@contextmanager
def open_plane(path):
    """Read level zero of a single-channel 2D mosaic by window."""
    with tifffile.TiffFile(path) as tif:
        series = tif.series[0]
        if series.axes != "YX" or series.dtype.name not in {"uint8", "uint16"}:
            raise ValueError(f"Expected a single-channel uint8 or uint16 YX mosaic: {path}")
        with series.aszarr(level=0) as store:
            yield zarr.open_array(store=store, mode="r")


def base_tiles(arrays, radii, dtype):
    for array, radius in zip(arrays, radii):
        height, width = array.shape
        halo = 2 * radius  # erosion and dilation each need one radius
        for y in range(0, height, TILE_SIZE):
            for x in range(0, width, TILE_SIZE):
                y1, x1 = min(y + TILE_SIZE, height), min(x + TILE_SIZE, width)
                y0, x0 = max(y - halo, 0), max(x - halo, 0)
                block = array[y0 : y1 + halo, x0 : x1 + halo]
                if radius:
                    size = 2 * radius + 1
                    block = white_tophat(block, size=(size, size), mode="reflect")
                    block = block[y - y0 : y1 - y0, x - x0 : x1 - x0]
                yield np.ascontiguousarray(block, dtype=dtype)


def subresolution_tiles(path, previous_level, shape, num_channels, dtype):
    """Reduce the previous TIFF level a tile at a time, keeping odd edge pixels."""
    height, width = shape
    with tifffile.TiffFile(path) as tif:
        for channel_index in range(num_channels):
            page = tif.pages[channel_index]
            if previous_level:
                page = page.pages[previous_level - 1]
            with page.aszarr() as store:
                array = zarr.open_array(store=store, mode="r")
                for y in range(0, height, TILE_SIZE):
                    for x in range(0, width, TILE_SIZE):
                        block = array[
                            2 * y : 2 * (y + TILE_SIZE),
                            2 * x : 2 * (x + TILE_SIZE),
                        ]
                        h, w = block.shape
                        if h % 2 or w % 2:
                            block = np.pad(block, ((0, h % 2), (0, w % 2)), mode="edge")
                        reduced = block.reshape(
                            (h + 1) // 2, 2, (w + 1) // 2, 2
                        ).mean(axis=(1, 3), dtype=np.float32)
                        yield np.rint(reduced).astype(dtype)


def write_pyramid(path, channels, arrays, radii, pixel_size_um, dtype, shapes):
    """Write an OME base level and reduced-resolution SubIFDs for every channel."""
    image_args = {
        "dtype": dtype,
        "tile": (TILE_SIZE, TILE_SIZE),
        "photometric": "minisblack",
        "compression": "deflate",
        "maxworkers": 1,
    }
    with tifffile.TiffWriter(path, ome=True, bigtiff=True) as tif:
        tif.write(
            base_tiles(arrays, radii, dtype),
            shape=(len(channels), *shapes[0]),
            metadata={
                "axes": "CYX",
                "Channel": {"Name": channels},
                "PhysicalSizeX": pixel_size_um,
                "PhysicalSizeY": pixel_size_um,
                "PhysicalSizeXUnit": "µm",
                "PhysicalSizeYUnit": "µm",
            },
            subifds=len(shapes) - 1,
            **image_args,
        )
        for level, shape in enumerate(shapes[1:]):
            tif.filehandle.flush()
            tif.write(
                subresolution_tiles(path, level, shape, len(channels), dtype),
                shape=(len(channels), *shape),
                subfiletype=1,
                metadata=None,
                **image_args,
            )


def plane_presets(channels, arrays, settings, overlays, display_mapping):
    default_color = [255, 255, 255]
    colors = {}
    limits = {}
    for channel, array in zip(channels, arrays):
        default_limits = [0, int(np.iinfo(array.dtype).max)]
        if display_mapping:
            options = settings[channel]
            color = options.get("color", default_color)
            lo, hi = options.get("limits", default_limits)
            if len(color) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in color):
                raise ValueError(f"Expected three RGB values from 0 to 255 for {channel}")
            if not math.isfinite(lo) or not math.isfinite(hi) or lo >= hi:
                raise ValueError(f"Expected finite increasing display limits for {channel}")
            colors[channel], limits[channel] = color, [lo, hi]
        else:
            colors[channel], limits[channel] = default_color, default_limits

    presets = {}
    for name, members in overlays.items():
        # The names are user-supplied references to this image's channel keys.
        if not members or len(set(members)) != len(members):
            raise ValueError(f"Overlay {name} must select one or more distinct channels")
        if set(members) - set(channels):
            raise ValueError(f"Overlay {name} uses unavailable channels: {set(members) - set(channels)}")
        presets[name] = {
            "selections": [{"c": channels.index(channel), "z": 0, "t": 0} for channel in members],
            "colors": [colors[channel] for channel in members],
            "contrastLimits": [limits[channel] for channel in members],
            "channelsVisible": [True] * len(members),
        }
    return presets


def write_png_previews(path, plane, overlays, level_shapes):
    """Render the overlay presets from a bounded level of the finished TIFF."""
    level = next(i for i, shape in enumerate(level_shapes) if max(shape) <= PNG_MAX_EDGE_PX)
    shape = level_shapes[level]
    with tifffile.TiffFile(path) as tif:
        preview = tif.series[0].levels[level]
        pixels = preview.asarray()
        if preview.axes == "YX":
            pixels = pixels[None, ...]

    filenames = {}
    for index, (name, preset) in enumerate(overlays.items(), start=1):
        rgb = np.zeros((*shape, 3), dtype=np.float32)
        for selection, color, (lo, hi) in zip(
            preset["selections"], preset["colors"], preset["contrastLimits"]
        ):
            intensity = (pixels[selection["c"]].astype(np.float32) - lo) / (hi - lo)
            np.clip(intensity, 0, 1, out=intensity)
            rgb += intensity[..., None] * np.asarray(color, dtype=np.float32)
        np.clip(rgb, 0, 255, out=rgb)
        np.rint(rgb, out=rgb)
        label = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")[:64] or "overlay"
        name_png = f"{plane}_{index:02d}_{label}.png"
        Image.fromarray(rgb.astype(np.uint8)).save(path.parent / name_png)
        filenames[name] = name_png
    print(f"[DISPLAY] {plane}: wrote {len(filenames)} PNG previews at {shape[1]} × {shape[0]} px")
    return {"shape_yx": shape, "pyramid_level": level, "overlays": filenames}


def prepare_display(
    input_manifest,
    display_profile,
    output_dir,
    subtract_background,
    apply_display_mapping,
):
    manifest = json.loads(input_manifest.read_text())
    profile = json.loads(display_profile.read_text())
    pixel_size_um = float(manifest["pixel_size_um"])
    if not math.isfinite(pixel_size_um) or pixel_size_um <= 0:
        raise ValueError("pixel_size_um must describe a positive image pixel spacing")
    planes = manifest["planes"]
    if not planes:
        raise ValueError("The display input must select one or more planes")
    # Plane keys name files, so allow only MIP or explicit 1-based Z labels.
    for plane in planes:
        if not re.fullmatch(r"mip|z0*[1-9][0-9]*", plane):
            raise ValueError(f"Expected mip or a 1-based Z label such as z020: {plane}")
    global_settings = profile.get("channels", {})
    global_overlays = profile.get("overlays", {})
    plane_overrides = profile.get("planes", {})
    output_dir.mkdir(parents=True, exist_ok=False)
    presets = {
        "subtract_background": subtract_background,
        "apply_display_mapping": apply_display_mapping,
        "pixel_size_um": pixel_size_um,
        "planes": {},
    }

    for plane, files in planes.items():
        paths = {
            channel: (input_manifest.parent / path).resolve()
            for channel, path in files.items()
        }
        channels = list(paths)
        overrides = plane_overrides.get(plane, {})
        local_settings = overrides.get("channels", {})
        settings = {
            c: global_settings.get(c, {}) | local_settings.get(c, {}) for c in channels
        }
        overlays = overrides.get("overlays", global_overlays)
        if not overlays:
            overlays = {channel: [channel] for channel in channels}
        radii = [0] * len(channels)
        if subtract_background:
            radii = [settings[c].get("background_radius_px", 0) for c in channels]
        if any(type(r) is not int or r < 0 for r in radii):
            raise ValueError(f"Background radii must be nonnegative integers for {plane}")
        print(f"[DISPLAY] {plane}: opening {len(channels)} input channels")
        with ExitStack() as stack:
            arrays = [stack.enter_context(open_plane(path)) for path in paths.values()]
            # These independently supplied planes must already share a pixel grid.
            # Equal shapes are necessary for stacking but do not establish alignment.
            shapes = {array.shape for array in arrays}
            if len(shapes) != 1:
                raise ValueError(f"Channels for {plane} must share one canvas shape: {shapes}")
            shape = shapes.pop()
            level_shapes = [shape]
            while max(level_shapes[-1]) > TILE_SIZE:
                h, w = level_shapes[-1]
                level_shapes.append(((h + 1) // 2, (w + 1) // 2))

            # Promote mixed uint8 and uint16 by casting the stored values exactly.
            dtype = np.result_type(*(array.dtype for array in arrays))
            groups = plane_presets(channels, arrays, settings, overlays, apply_display_mapping)
            output_image = output_dir / f"{plane}.ome.tif"
            print(f"[DISPLAY] {plane}: writing {len(level_shapes)} resolutions to {output_image}")
            write_pyramid(
                output_image, channels, arrays, radii, pixel_size_um, dtype, level_shapes
            )
        presets["planes"][plane] = {
            "image": output_image.name,
            "channels": channels,
            "shape_yx": shape,
            "dtype": dtype.name,
            "background_radius_px": dict(zip(channels, radii)),
            "overlays": groups,
            "png_preview": write_png_previews(output_image, plane, groups, level_shapes),
        }

    with (output_dir / "display_presets.json").open("x") as handle:
        json.dump(presets, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input_manifest", required=True, type=Path)
    parser.add_argument("--display_profile", required=True, type=Path)
    parser.add_argument("--output_dir", required=True, type=Path)
    parser.add_argument("--subtract_background", action="store_true")
    parser.add_argument("--apply_display_mapping", action="store_true")
    prepare_display(**vars(parser.parse_args()))
