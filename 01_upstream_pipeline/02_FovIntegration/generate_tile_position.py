#!/usr/bin/env python3
# generate_tile_position.py
# Pre-generate FOV layout CSV based on scanning pattern

import csv
import argparse


def generate_fov_grid(rows, cols, start_num, scan_type, primary_dir, secondary_dir):
    """
    Generate a 2D grid of FOV numbers based on scanning parameters.

    Parameters:
        rows (int): Number of rows in the grid.
        cols (int): Number of columns in the grid.
        start_num (int): Starting FOV number.
        scan_type (str): 'R' for raster scan, 'S' for snake scan.

        primary_dir (str): First scan direction ('L', 'R', 'U', 'D').
        secondary_dir (str): Second scan direction ('L', 'R', 'U', 'D').

    Returns:
        list[list[int]]: 2D grid with FOV numbers.
    """
    # Initialize grid array
    grid = [[0 for _ in range(cols)] for _ in range(rows)]
    fov_counter = start_num

    horizontal = {'L', 'R'}
    vertical = {'U', 'D'}

    # Row-major scanning (primary direction is horizontal)
    if primary_dir in horizontal:
        row_indices = list(range(rows))
        if secondary_dir == 'U':
            row_indices = reversed(row_indices)          # Reverse order if secondary is up

        for i in row_indices:
            col_indices = list(range(cols))
            is_reversed = (scan_type == 'S' and i % 2 != 0)    # Reverse order for snake scan, index is 0-based

            # Determine actual scan direction for this row
            if (primary_dir == 'R' and not is_reversed) or \
               (primary_dir == 'L' and is_reversed):
                # Left to right
                for j in col_indices:
                    grid[i][j] = fov_counter
                    fov_counter += 1
            else:
                # Right to left
                for j in reversed(col_indices):
                    grid[i][j] = fov_counter
                    fov_counter += 1

    # Column-major scanning (primary direction is vertical)
    else:  # primary_dir in vertical
        col_indices = list(range(cols))
        if secondary_dir == 'L':
            col_indices = reversed(col_indices)

        for j in col_indices:
            row_indices = list(range(rows))
            is_reversed = (scan_type == 'S' and j % 2 != 0)

            if (primary_dir == 'D' and not is_reversed) or \
               (primary_dir == 'U' and is_reversed):
                # Top to bottom
                for i in row_indices:
                    grid[i][j] = fov_counter
                    fov_counter += 1
            else:
                # Bottom to top
                for i in reversed(row_indices):
                    grid[i][j] = fov_counter
                    fov_counter += 1

    return grid


def save_to_csv(grid, filename):
    """Save the FOV grid to a CSV file."""
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(grid)
        print(f"Successfully created file: '{filename}'")
    except IOError as e:
        print(f"Error writing to file '{filename}': {e}")


def validate_directions(primary, secondary):
    """Validate that directions are orthogonal and valid."""
    valid = {'L', 'R', 'U', 'D'}
    horizontal = {'L', 'R'}
    vertical = {'U', 'D'}

    if primary not in valid or secondary not in valid:
        raise ValueError("Primary and secondary directions must be one of: L, R, U, D")

    if (primary in horizontal and secondary in vertical) or \
       (primary in vertical and secondary in horizontal):
        return True
    else:
        raise ValueError("Primary and secondary directions must be orthogonal "
                         "(e.g., horizontal + vertical)")


def main():
    parser = argparse.ArgumentParser(
        description="Generate a CSV file representing FOV numbering layout "
                    "based on scanning pattern (raster or snake)."
    )
    parser.add_argument("--rows", type=int, required=True,
                        help="Number of rows in the FOV grid (positive integer).")
    parser.add_argument("--cols", type=int, required=True,
                        help="Number of columns in the FOV grid (positive integer).")
    parser.add_argument("--start", type=int, default=1,
                        help="Starting FOV number (default: 1).")
    parser.add_argument("--scan", choices=['R', 'S'], required=True,
                        help="Scan type: 'R' for raster (row-by-row), 'S' for snake.")
    parser.add_argument("--primary", choices=['L', 'R', 'U', 'D'], required=True,
                        help="Primary scan direction: L=Left, R=Right, U=Up, D=Down.")
    parser.add_argument("--secondary", choices=['L', 'R', 'U', 'D'], required=True,
                        help="Secondary scan direction (must be orthogonal to primary).")
    parser.add_argument("--output", type=str, default="fov_layout.csv",
                        help="Output CSV filename (default: fov_layout.csv).")

    args = parser.parse_args()

    # Validate inputs
    if args.rows <= 0 or args.cols <= 0:
        parser.error("Rows and columns must be positive integers.")

    try:
        validate_directions(args.primary, args.secondary)
    except ValueError as e:
        parser.error(str(e))

    # Generate grid
    grid = generate_fov_grid(
        rows=args.rows,
        cols=args.cols,
        start_num=args.start,
        scan_type=args.scan,
        primary_dir=args.primary,
        secondary_dir=args.secondary
    )

    # Print grid to console
    print("\nGenerated FOV grid:")
    for row in grid:
        print('\t'.join(map(str, row)))

    # Save to CSV
    save_to_csv(grid, args.output)


if __name__ == "__main__":
    main()