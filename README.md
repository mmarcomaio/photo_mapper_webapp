#     Synology Photo Map Search

A lightweight, self-hosted web application designed for Synology NAS (tested on DS218j) to index photos from local directories, extract GPS metadata, and display them on an interactive world map.

##     Features
* **Interactive Map:** Clickable SVG world map (Blue = Visited, Gray = Unvisited).
* **Metadata Extraction:** Automatically parses EXIF data from `.jpg` and `.jpeg` files.
* **Smart Search:** Search by city, region, or country.
* **Admin Dashboard:** Manage watched folders, scan frequency, and database maintenance.

##      Installation & Setup

### 1. Prerequisites
Ensure Python 3 is installed on your Synology via the Package Center.

### 2. Preparation
If you haven't created the environment yet, run:
```bash
python3 -m venv webappenv
```

and install the dependencies
```bash
source webappenv/bin/activate
pip install -r pip_requirements.txt
```

### 3.     Running the App
To start the server manually:
```bash
1. Enter the directory
cd /volume1/web/photo_map
2. Activate your specific environment
source webappenv/bin/activate
3. Launch the application
python3 app.py
The app will be available at http://<your-nas-ip>:5005.
```