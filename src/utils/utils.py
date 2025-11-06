# Copyright (c) 2024
# __author__ = "Dean Hand"
# __license__ = "AGPL"
# __version__ = "1.0"
import pandas as pd
import os
import warnings
import re
import glob

import warnings
from typing import List, Optional, Literal, Tuple


class Color:
    """Defines color codes for console output."""
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    DARKCYAN = "\033[36m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    ORANGE = "\033[0;33m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"
    DARKMAGENTA = "\033[0;35m"
    DARKGREEN = "\033[0;32m"

    def __init__(self):
        """Initializes the Color object with default color settings."""
        self.color = self.PURPLE
        self.color = self.BLUE
        self.color = self.GREEN
        self.color = self.YELLOW
        self.color = self.RED
        self.color = self.BOLD
        self.color = self.UNDERLINE
        self.color = self.END
        self.color = self.DARKMAGENTA


def read_sensor_dimensions_from_csv(csv_filepath, default_sensor_width=0, default_sensor_height=0, default_lens_FOVw=0,
                                    default_lens_FOVh=0):
    """
    Reads sensor dimensions from a CSV file, returning a dictionary with sensor models and camera index as keys
    and tuples of sensor dimensions as values. If sensor dimensions are not found, default values are used.

    Parameters:
    - csv_filepath (str): Path to the CSV file containing sensor dimensions.
    - default_sensor_width (float, optional): Default sensor width if a model is not found in the CSV.
    - default_sensor_height (float, optional): Default sensor height if a model is not found in the CSV.
    - default_lens_FOVw (float, optional): Default lens FOVw if a model is not found in the CSV.
    - default_lens_FOVh (float, optional): Default lens FOVh if a model is not found in the CSV.

    Returns:
    - dict: A dictionary with (sensor model, rig camera index) as keys and sensor dimensions as values.
    """
    sensor_dimensions = {}
    try:
        df = pd.read_csv(csv_filepath)
        for _, row in df.iterrows():
            drone_make = row["DroneMake"]
            drone_model = row["DroneModel"]
            camera_make = row["CameraMake"]
            sensor_model = row["SensorModel"]
            # Handle missing RigCameraIndex as 'default'
            cam_index = row.get("RigCameraIndex", 'default')
            width = row.get("SensorWidth", default_sensor_width)
            height = row.get("SensorHeight", default_sensor_height)
            lens_FOVw = row.get("LensFOVw", default_lens_FOVw)
            lens_FOVh = row.get("LensFOVh", default_lens_FOVh)

            # Construct the key with care for default values
            key = (sensor_model, str(cam_index))
            sensor_dimensions[key] = (
            drone_make, drone_model, camera_make, sensor_model, str(cam_index), width, height, lens_FOVw, lens_FOVh)

        # Ensure a 'default' entry exists in the dictionary
        if ("default", 'default') not in sensor_dimensions:
            sensor_dimensions[("default", 'default')] = (
            "Unknown", "Unknown", "Unknown", "default", 'default', default_sensor_width, default_sensor_height,
            default_lens_FOVw, default_lens_FOVh)

    except FileNotFoundError:
        warnings.warn(f"Error: The file {csv_filepath} was not found.")
    except pd.errors.EmptyDataError:
        warnings.warn("Error: The CSV file is empty.")
    except Exception as e:
        warnings.warn(f"An unexpected error occurred: {e}")
    return sensor_dimensions


def _resolve_paths(
    mode: Literal["search", "create", "match", "name"],
    input: str | List[str],
    *,
    kwargs: dict | None = None,
) -> List[str]:
    """
    Resolves a list of input based on the mode and input format.

    Args:
        mode (Literal["search", "create", "match", "name"]): Type of operation to perform.
        input (str | List[str]): Either a list of file input or a folder/template string.
        kwargs (dict, optional): Additional keyword arguments passed to the resolved function.

    Returns:
        List[str]: List of resolved input.
    """
    kwargs = kwargs or {}

    if mode == "name":
        resolved = [os.path.splitext(os.path.basename(p))[0] for p in input]
    elif isinstance(input, list):
        resolved = input
    elif mode == "search":
        resolved = search_paths(input, **kwargs)
    elif mode == "create":
        resolved = create_paths(input, **kwargs)
    elif mode == "match":
        resolved = match_paths(**kwargs)
    else:
        raise ValueError(f"Invalid mode: {mode}")

    if len(resolved) == 0:
        warnings.warn("No results found for paths.", RuntimeWarning)

    return resolved


def search_paths(
    search_pattern: str,
    *,
    default_file_pattern: str | None = None,
    recursive: bool = False,
    match_to_paths: Tuple[List[str], str] | None = None,
    debug_logs: bool = False,
) -> List[str]:
    """
    Search for files using a glob pattern, or a folder with a default file pattern.

    Args:
        search_pattern (str, required): Defines input files from a glob path or folder. Specify like: "/input/files/*.tif" or "/input/folder" (while passing default_file_pattern like: '*.tif')
        default_file_pattern (str, optional): Used when `pattern` is a directory. If not set and `pattern` is a folder, raises an error.
        recursive (bool, optional): Whether to search recursively.
        match_to_paths (Tuple[List[str], str], optional): Matches input files to a reference list using a regex.
        debug_logs (bool, optional): Whether to print matched paths.

    Returns:
        List[str]: Sorted list of matched file paths.

    Raises:
        ValueError: If `search_pattern` is a directory and `default_file_pattern` is not provided.
    """
    if not os.path.basename(search_pattern).count("."):
        if not default_file_pattern:
            raise ValueError(
                "Pattern is a directory, but no default_file_pattern was provided."
            )
        search_pattern = os.path.join(search_pattern, default_file_pattern)

    input_paths = sorted(glob.glob(search_pattern, recursive=recursive))

    if debug_logs:
        print(f"Found {len(input_paths)} file(s) matching: {search_pattern}")

    if match_to_paths:
        input_paths = match_paths(input_paths, *match_to_paths)

    return input_paths


def create_paths(
    template_pattern: str,
    paths_or_bases: List[str],
    *,
    default_file_pattern: str | None = None,
    debug_logs: bool = False,
    replace_symbol: str = "$",
    create_folders: bool = True,
) -> List[str]:
    """
    Create output paths using a filename template_pattern and a list of reference paths or names.

    Args:
        template_pattern (str, required): Defines output files from a glob path or folder to match input paths or names. Specify like: "/input/files/$.tif" or "/input/folder" (while passing default_file_pattern like: '$.tif')
        paths_or_bases (List[str]): List of full paths or base names to derive the replace_symbol from.
        default_file_pattern (str, optional): Used if `template_pattern` is a directory.
        debug_logs (bool): Whether to print the created paths.
        replace_symbol (str): Placeholder symbol in the template to replace with base names.
        create_folders (bool): Whether to create output folders if they don't exist.

    Returns:
        List[str]: List of constructed file paths.

    Raises:
        ValueError: If `template_pattern` is a directory and `default_file_pattern` is not provided.
    """
    if not os.path.basename(template_pattern).count("."):
        if not default_file_pattern:
            raise ValueError(
                "Template is a directory, but no default_file_pattern was provided."
            )
        template_pattern = os.path.join(template_pattern, default_file_pattern)

    output_paths = []
    for ref in paths_or_bases:
        base = (
            os.path.splitext(os.path.basename(ref))[0]
            if ("/" in ref or "\\" in ref)
            else os.path.splitext(ref)[0]
        )
        filename = template_pattern.replace(replace_symbol, base)
        output_paths.append(filename)

    if create_folders:
        for path in output_paths:
            os.makedirs(os.path.dirname(path), exist_ok=True)

    if debug_logs:
        print(f"Created {len(output_paths)} paths:")
        for p in output_paths:
            print(f"  {p}")

    return output_paths


def match_paths(
    input_match_paths: List[str],
    reference_paths: List[str],
    match_regex: str,
    debug_logs: bool = False,
) -> List[Optional[str]]:
    """
    Match `reference_paths` to `input_match_paths` using a regex applied to the basenames of `input_match_paths`. The extracted key must be a substring of the reference filename.

    Args:
        input_match_paths (List[str]): List of candidate paths to extract keys from.
        reference_paths (List[str]): List of reference paths to align to.
        match_regex (str): Regex applied to basenames of input_match_paths to extract a key to match via *inclusion* in reference_paths (e.g. "(.*)_LocalMatch\\.gpkg$" (without one of the backslashes)).
        debug_logs (bool): If True, print matched and unmatched file basenames.

    Returns:
        List[Optional[str]]: A list the same length as `reference_paths` where each
        element is the matched path from `input_match_paths` or None.

    Raises:
        ValueError: If output list length does not match reference_paths length.
    """
    pattern = re.compile(match_regex)
    match_keys = {}
    used_matches = set()

    # Extract keys from input_match_paths
    for mpath in input_match_paths:
        basename = os.path.basename(mpath)
        match = pattern.search(basename)
        if not match:
            continue
        key = match.group(1) if match.groups() else match.group(0)
        match_keys[key] = mpath

    # Match each reference path
    matched_list: List[Optional[str]] = []
    for rpath in reference_paths:
        rbase = os.path.basename(rpath)
        matched = None
        for key, mpath in match_keys.items():
            if key in rbase:
                matched = mpath
                used_matches.add(mpath)
                break
        matched_list.append(matched)

    # Validate output length
    if len(matched_list) != len(reference_paths):
        raise ValueError("Matched list length does not match reference_paths length.")

    return matched_list
