# 📸 MementoSync

**MementoSync** is a tool designed to fix missing metadata in Google Takeout photos. It reads the accompanying `.json` files (e.g., `photo.jpg.json`) provided by Google Takeout and injects the correct `Date Taken` and `GPS` data back into the original images.

## Features

-   **Metadata Injection**: Restores original 'Date Taken' and GPS coordinates from JSON sidecars.
-   **EXIF Preservation**: Preserves existing camera metadata (ISO, Aperture, Model) if present in the original file.
-   **Large File Support**: Optimized for large backups (up to 15GB) using disk-based processing to minimize RAM usage.
-   **Smart Matching**: Handles various JSON naming conventions (`img.jpg.json`, `img.json`, `img.supplemental-metadata.json`).

## Quick Start (Docker)

The easiest way to run MementoSync is using Docker.

1.  **Clone the repository** (or download the files).
2.  **Run with Docker Compose**:
    ```bash
    docker compose up -d --build
    ```
3.  **Access the App**:
    Open your browser and navigate to [http://localhost:8501](http://localhost:8501).

## Manual Installation

If you prefer to run it locally without Docker:

1.  **Install Requirements**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Run Streamlit**:
    ```bash
    streamlit run app.py
    ```

## Usage

1.  Upload your Google Takeout ZIP file.
2.  Click **Process Photos**.
3.  Wait for the processing to complete (progress bar will update).
4.  Download the corrected ZIP file (`[original_name]_fixed.zip`).

## Notes

-   **Google Photos Quality**: If your photos were stored in "Storage Saver" quality on Google Photos, they might lack original camera metadata (ISO, Aperture, etc.). This tool cannot restore data that was stripped by Google, but it *will* restore the Date and Location provided in the JSONs.
-   **Disk Space**: The tool requires temporary disk space approximately 3x the size of your upload to process the files.
