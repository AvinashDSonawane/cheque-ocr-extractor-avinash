"""
image_loader.py
---------------
Loads images from a given folder, prepares a list of image paths,
and optionally loads images into memory as OpenCV arrays.
"""

import os
import glob
import cv2
from typing import List, Tuple, Optional

# Supported image extensions
# FIX (Bug 3): '.tif' was missing its leading dot, causing it to never match
# os.path.splitext() comparisons. Corrected to '.tif'.
SUPPORTED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')


def get_image_paths(folder_path: str) -> List[str]:
    """
    Scans a folder and returns a list of full paths to image files.
    
    Args:
        folder_path (str): Path to the folder containing cheque images.
        
    Returns:
        List[str]: Sorted list of image file paths.
    """
    if not os.path.isdir(folder_path):
        raise ValueError(f"Invalid folder path: {folder_path}")
    
    # Collect all files with supported extensions
    image_paths = []
    for ext in SUPPORTED_EXTENSIONS:
        pattern = os.path.join(folder_path, f"*{ext}")
        image_paths.extend(glob.glob(pattern))
    
    # Sort to maintain consistent order
    image_paths.sort()
    return image_paths


def load_image_as_array(image_path: str) -> Optional[cv2.Mat]:
    """
    Loads a single image using OpenCV and returns it as a BGR numpy array.
    
    Args:
        image_path (str): Full path to the image file.
        
    Returns:
        Optional[cv2.Mat]: Image array if successful, else None.
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"Warning: Could not load image: {image_path}")
        return None
    return img


def load_all_images(folder_path: str) -> Tuple[List[str], List[cv2.Mat]]:
    """
    Loads all images from a folder into memory.
    
    Args:
        folder_path (str): Path to the folder.
        
    Returns:
        Tuple[List[str], List[cv2.Mat]]: Two lists – image paths and corresponding loaded arrays.
    """
    paths = get_image_paths(folder_path)
    images = []
    valid_paths = []
    for p in paths:
        img = load_image_as_array(p)
        if img is not None:
            valid_paths.append(p)
            images.append(img)
    return valid_paths, images


if __name__ == "__main__":
    # Quick test (you can remove this later)
    test_folder = input("Enter folder path to test image loader: ").strip()
    paths, images = load_all_images(test_folder)
    print(f"Found {len(paths)} images.")
    for p in paths:
        print(f"  - {os.path.basename(p)}")