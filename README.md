This script converts CBR (RAR) and CBZ (ZIP) files into uncompressed CBZ format while preserving the directory structure.
It uses multithreading for faster processing and includes progress indication.

**Dependencies**:
- pip install rarfile tqdm
- sudo apt install unrar (Linux only)
- For Windows, install WinRAR and ensure it's in your PATH


**Usage**:
    Basic usage:
        python convert_comics.py /path/to/input/comics /path/to/output/directory

    With specific number of threads:
        python convert_comics.py /path/to/input/comics /path/to/output/directory --threads 4


**Features**:
    - Processes CBR and CBZ files recursively in the input directory
    - Preserves directory structure in the output
    - Converts all files to uncompressed CBZ format
    - Multi-threaded processing for improved speed
    - Progress bar showing conversion status
    - Detailed error logging to 'conversion.log'
    - Moves problematic files to '_failed' subdirectory
    - Attempts to recover misnamed archives (e.g., CBR files that are actually ZIP)
    - Full Unicode/non-ASCII filename support


**Output Structure**:
    output_directory/
    ├── [preserved directory structure with converted CBZ files]
    └── _failed/
        └── [preserved directory structure with failed files]


**Log File**:
    - Creates 'conversion.log' in the current directory
    - Contains detailed error messages and conversion status
    - Useful for debugging failed conversions

**Error Handling**:
    - Failed conversions don't stop the script
    - All errors are logged to both console and log file
    - Problematic files are moved to '_failed' directory
    - Temporary files are cleaned up even after errors

**Performance Tips**:
    - Default thread count is set to CPU count
    - For HDDs, using too many threads might slow down processing
    - For SSçDs, higher thread counts generally improve performance
    - Monitor system resources and adjust thread count as needed

