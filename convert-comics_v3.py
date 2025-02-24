import os
import shutil
import zipfile
import rarfile
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import logging
from queue import Queue
from threading import Lock
import sys
import pathlib

"""
This script converts CBR (RAR) and CBZ (ZIP) files into uncompressed CBZ format while preserving the directory structure.
It uses multithreading for faster processing and includes progress indication.

Dependencies:
- pip install rarfile tqdm
- sudo apt install unrar (Linux only)
- For Windows, install WinRAR and ensure it's in your PATH

Usage:
    Basic usage:
        python convert_comics.py /path/to/input/comics /path/to/output/directory

    With specific number of threads:
        python convert_comics.py /path/to/input/comics /path/to/output/directory --threads 4

Features:
    - Processes CBR and CBZ files recursively in the input directory
    - Preserves directory structure in the output
    - Converts all files to uncompressed CBZ format
    - Multi-threaded processing for improved speed
    - Progress bar showing conversion status
    - Detailed error logging to 'conversion.log'
    - Moves problematic files to '_failed' subdirectory
    - Attempts to recover misnamed archives (e.g., CBR files that are actually ZIP)
    - Full Unicode/non-ASCII filename support

Output Structure:
    output_directory/
    ├── [preserved directory structure with converted CBZ files]
    └── _failed/
        └── [preserved directory structure with failed files]

Log File:
    - Creates 'conversion.log' in the current directory
    - Contains detailed error messages and conversion status
    - Useful for debugging failed conversions

Error Handling:
    - Failed conversions don't stop the script
    - All errors are logged to both console and log file
    - Problematic files are moved to '_failed' directory
    - Temporary files are cleaned up even after errors

Performance Tips:
    - Default thread count is set to CPU count
    - For HDDs, using too many threads might slow down processing
    - For SSDs, higher thread counts generally improve performance
    - Monitor system resources and adjust thread count as needed
"""

# Configure UTF-8 encoding for all platforms
if sys.platform.startswith('win'):
    # Force UTF-8 on Windows
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Set up logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('conversion.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Shared counters with thread-safe access
class Counter:
    def __init__(self):
        self.lock = Lock()
        self.processed = 0
        self.converted = 0
        self.failed = 0
    
    def increment(self, counter_type):
        with self.lock:
            if counter_type == 'processed':
                self.processed += 1
            elif counter_type == 'converted':
                self.converted += 1
            elif counter_type == 'failed':
                self.failed += 1

counter = Counter()

def safe_path(path):
    """Convert path to pathlib.Path for safe path handling."""
    return pathlib.Path(path)

def is_valid_zip(zip_path):
    """Check if a ZIP file is valid."""
    try:
        with zipfile.ZipFile(str(zip_path), 'r') as z:
            return z.testzip() is None
    except (zipfile.BadZipFile, Exception) as e:
        logging.error(f"Error checking ZIP file {zip_path}: {str(e)}")
        return False

def is_valid_rar(rar_path):
    """Check if a RAR file is valid."""
    try:
        with rarfile.RarFile(str(rar_path), 'r') as r:
            return r.testrar() is None
    except (rarfile.BadRarFile, Exception) as e:
        logging.error(f"Error checking RAR file {rar_path}: {str(e)}")
        return False

def safe_extract(archive, temp_dir):
    """Safely extract archive handling potential encoding issues."""
    for info in archive.infolist():
        try:
            # Handle potentially corrupted filenames
            try:
                # Try UTF-8 first
                filename = info.filename.encode('cp437').decode('utf-8')
            except UnicodeEncodeError:
                # If that fails, try the original filename
                filename = info.filename
            except UnicodeDecodeError:
                # If both fail, try cp437
                filename = info.filename.encode('cp437').decode('cp437')
                
            # Convert filename to pathlib.Path for safe handling
            target_path = safe_path(temp_dir) / filename
            
            # Ensure the extraction path is within temp_dir
            if not str(target_path.absolute()).startswith(str(safe_path(temp_dir).absolute())):
                raise Exception(f"Attempted path traversal: {filename}")
            
            # Create parent directories if needed
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Extract the file
            archive.extract(info, str(temp_dir))
            
        except Exception as e:
            logging.error(f"Error extracting {info.filename}: {str(e)}")
            raise

def convert_to_cbz(src_file, dest_file, failed_path):
    """Convert a CBR or CBZ file into an uncompressed CBZ file."""
    src_file = safe_path(src_file)
    dest_file = safe_path(dest_file)
    failed_path = safe_path(failed_path)
    temp_dir = safe_path(str(dest_file) + "_temp")
    
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Extract files based on archive type
        if src_file.suffix.lower() == '.cbr':
            try:
                with rarfile.RarFile(str(src_file), 'r') as rf:
                    safe_extract(rf, temp_dir)
            except Exception as e:
                logging.error(f"Error extracting RAR {src_file}: {str(e)}")
                # Try opening as a ZIP file in case of misnamed CBR
                try:
                    if is_valid_zip(src_file):
                        with zipfile.ZipFile(str(src_file), 'r') as zf:
                            safe_extract(zf, temp_dir)
                    else:
                        raise Exception("Not a valid ZIP file either")
                except Exception as ze:
                    logging.error(f"Failed to process as ZIP: {str(ze)}")
                    failed_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, failed_path)
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir)
                    counter.increment('failed')
                    return False
        else:
            try:
                with zipfile.ZipFile(str(src_file), 'r') as zf:
                    safe_extract(zf, temp_dir)
            except Exception as e:
                logging.error(f"Error extracting ZIP {src_file}: {str(e)}")
                failed_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, failed_path)
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                counter.increment('failed')
                return False
        
        # Repack extracted files into an uncompressed CBZ archive
        try:
            with zipfile.ZipFile(str(dest_file), 'w', compression=zipfile.ZIP_STORED) as new_zip:
                for file_path in temp_dir.rglob('*'):
                    if file_path.is_file():
                        arcname = str(file_path.relative_to(temp_dir))
                        new_zip.write(file_path, arcname)
            counter.increment('converted')
            return True
        except Exception as e:
            logging.error(f"Error creating new ZIP {dest_file}: {str(e)}")
            failed_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, failed_path)
            counter.increment('failed')
            return False
    except Exception as e:
        logging.error(f"Unexpected error processing {src_file}: {str(e)}")
        failed_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, failed_path)
        counter.increment('failed')
        return False
    finally:
        # Clean up temporary extraction folder
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

def process_file(args):
    """Process a single file (for use with ThreadPoolExecutor)."""
    src_file, dest_file, failed_path = [safe_path(p) for p in args]
    counter.increment('processed')
    
    # Validate and convert files
    if src_file.suffix.lower() == '.cbz':
        if not is_valid_zip(src_file):
            failed_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, failed_path)
            counter.increment('failed')
            return False
    elif src_file.suffix.lower() == '.cbr':
        if not is_valid_rar(src_file):
            if not is_valid_zip(src_file):
                failed_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, failed_path)
                counter.increment('failed')
                return False
    
    return convert_to_cbz(src_file, dest_file, failed_path)

def process_files(input_dir, output_dir, max_workers=None):
    """Process all CBR/CBZ files in the input directory recursively using multiple threads."""
    input_dir = safe_path(input_dir)
    output_dir = safe_path(output_dir)
    failed_dir = output_dir / "_failed"
    
    # Collect all files to process
    files_to_process = []
    for src_file in input_dir.rglob('*'):
        if src_file.suffix.lower() in ('.cbz', '.cbr'):
            rel_path = src_file.relative_to(input_dir)
            dest_path = output_dir / rel_path.parent
            failed_path = failed_dir / rel_path
            dest_file = dest_path / (src_file.stem + ".cbz")
            dest_path.mkdir(parents=True, exist_ok=True)
            files_to_process.append((str(src_file), str(dest_file), str(failed_path)))
    
    # Process files using ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_file, args) for args in files_to_process]
        
        # Show progress bar
        with tqdm(total=len(files_to_process), desc="Converting files") as pbar:
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Unexpected error in thread: {str(e)}")
                pbar.update(1)
    
    # Summary
    logging.info(f"Processing complete: {counter.processed} files processed")
    logging.info(f"Converted: {counter.converted}, Failed: {counter.failed}")

if __name__ == "__main__":
    # Command-line argument parsing
    parser = argparse.ArgumentParser(description="Convert CBR/CBZ to uncompressed CBZ while preserving directory structure.")
    parser.add_argument("input_dir", help="Input directory containing CBR/CBZ files")
    parser.add_argument("output_dir", help="Output directory for processed files")
    parser.add_argument("--threads", type=int, help="Number of worker threads (default: CPU count)", default=None)
    args = parser.parse_args()
    
    process_files(args.input_dir, args.output_dir, args.threads)
