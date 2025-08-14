import torch
import os
import shutil
import kagglehub

def get_device(ngpu = 1):
    """ 
    Set device to GPU if available; otherwise CPU 
    Set to CPU mode if ngpu = 0 
    """
    device = torch.device("cuda" if (torch.cuda.is_available() and ngpu > 0)
                      else "mps" if (torch.backends.mps.is_available() and ngpu > 0)
                      else "xpu" if (torch.xpu.is_available() and ngpu > 0)
                      else "cpu")
    return device

# Downloads dataset from kaggle
def download_dataset(dataset, destination_dir):
    # Download latest version
    path = kagglehub.dataset_download(dataset)
    move_files_recursively(path, destination_dir)
    
def move_files_recursively(source_dir, destination_dir):
    """
    Moves all files and subdirectories from source_dir to destination_dir recursively.

    Args:
        source_dir (str): The path to the source directory.
        destination_dir (str): The path to the destination directory.
    """
    if not os.path.exists(source_dir):
        print(f"Source directory '{source_dir}' does not exist.")
        return
    
    # Create the destination directory if it doesn't exist
    os.makedirs(destination_dir, exist_ok=True)

    for root, dirs, files in os.walk(source_dir):
        # Calculate the relative path from the source_dir to the current root
        relative_path = os.path.relpath(root, source_dir)
        
        # Construct the corresponding destination path for the current root
        current_destination_path = os.path.join(destination_dir, relative_path)
        
        # Create subdirectories in the destination if they don't exist
        for d in dirs:
            os.makedirs(os.path.join(current_destination_path, d), exist_ok=True)

        # Move files from the current root to the destination
        for f in files:
            source_file_path = os.path.join(root, f)
            destination_file_path = os.path.join(current_destination_path, f)
            try:
                shutil.move(source_file_path, destination_file_path)
            except Exception as e:
                print(f"Error moving {source_file_path}: {e}")
