# File Operations

Space-Track provides several file-based endpoints beyond the standard query API. These operations are direct client methods -- they do not use the `SpaceTrackQuery` builder. The three subsystems are **FileShare** (authenticated file storage), **SP Ephemeris** (special perturbations ephemeris files), and **Public Files** (unauthenticated downloads).

For the complete API reference, see the [SpaceTrackClient Reference](../../../library_api/ephemeris/spacetrack/client.md).

## FileShare

The FileShare subsystem provides authenticated file storage on Space-Track.org. Users can upload, download, list, and delete files organized into folders.

### Listing Files and Folders

Retrieve metadata for all files or folders in your file share. Results are returned as typed records (`FileShareFileRecord` and `FolderRecord`).


```python
import brahe as bh

client = bh.SpaceTrackClient("user@example.com", "password")

# List all files
files = client.fileshare_list_files()
for f in files:
    print(f"ID: {f.file_id}, Name: {f.file_name}, Size: {f.file_size}")

# List all folders
folders = client.fileshare_list_folders()
for folder in folders:
    print(f"ID: {folder.folder_id}, Name: {folder.folder_name}")
```

### Uploading Files

Upload a file to a specific folder. The `file_data` parameter accepts raw bytes.


```python
import brahe as bh

client = bh.SpaceTrackClient("user@example.com", "password")

# Upload from bytes
response = client.fileshare_upload("100", "ephemeris.txt", b"file contents here")

# Upload from a file on disk
with open("local_data.csv", "rb") as f:
    response = client.fileshare_upload("100", "local_data.csv", f.read())
```

### Downloading Files

Download a single file by its ID, or download an entire folder as a zip archive.


```python
import brahe as bh

client = bh.SpaceTrackClient("user@example.com", "password")

# Download a single file (returns bytes)
data = client.fileshare_download("12345")
with open("downloaded.txt", "wb") as f:
    f.write(data)

# Download an entire folder (returns zip archive bytes)
zip_data = client.fileshare_download_folder("100")
with open("folder_archive.zip", "wb") as f:
    f.write(zip_data)
```

### Deleting Files

Delete a file by its ID.


```python
import brahe as bh

client = bh.SpaceTrackClient("user@example.com", "password")
response = client.fileshare_delete("12345")
```

## SP Ephemeris

The SP Ephemeris subsystem provides access to Special Perturbations ephemeris files. These are higher-fidelity orbital predictions than the standard GP (General Perturbations) data. All SP Ephemeris operations require authentication.

### Listing Ephemeris Files

List available SP ephemeris files. Each record includes the associated NORAD catalog ID and the epoch coverage interval.


```python
import brahe as bh

client = bh.SpaceTrackClient("user@example.com", "password")

files = client.spephemeris_list_files()
for f in files:
    print(f"ID: {f.file_id}, Object: {f.norad_cat_id}, "
          f"Epoch: {f.epoch_start} to {f.epoch_stop}")
```

### Downloading Ephemeris Files

Download an SP ephemeris file by its file ID.


```python
import brahe as bh

client = bh.SpaceTrackClient("user@example.com", "password")

data = client.spephemeris_download("99999")
with open("iss_sp.e", "wb") as f:
    f.write(data)
```

### File History

Retrieve the version history for SP ephemeris files. The response is returned as generic JSON since the schema is not fixed.


```python
import brahe as bh

client = bh.SpaceTrackClient("user@example.com", "password")

history = client.spephemeris_file_history()
for record in history:
    print(record)
```

## Public Files

The Public Files subsystem provides access to publicly available files on Space-Track.org. These operations **do not require authentication**, though the client must still be instantiated (credentials are not sent for these requests).

### Listing Directories

List available public file directories. The response is returned as generic JSON.


```python
import brahe as bh

client = bh.SpaceTrackClient("user@example.com", "password")

dirs = client.publicfiles_list_dirs()
for d in dirs:
    print(d)
```

### Downloading Public Files

Download a public file by name.


```python
import brahe as bh

client = bh.SpaceTrackClient("user@example.com", "password")

data = client.publicfiles_download("catalog.txt")
with open("catalog.txt", "wb") as f:
    f.write(data)
```

---

## See Also

- [Space-Track API Overview](index.md) -- Module architecture and type catalog
- [Client](client.md) -- Authentication, query execution, and response handling
- [SpaceTrackClient Reference](../../../library_api/ephemeris/spacetrack/client.md) -- Complete method documentation
- [Response Types Reference](../../../library_api/ephemeris/spacetrack/responses.md) -- All response type field definitions