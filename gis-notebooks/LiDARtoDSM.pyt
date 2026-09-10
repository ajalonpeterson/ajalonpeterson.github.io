# -*- coding: utf-8 -*-
"""
LiDAR Processing Toolbox
=========================
A custom ArcGIS Python Toolbox that automates the full path from raw LiDAR
tiles to a usable Digital Surface Model (DSM): downloads a batch of LAZ
files from a URL list, decompresses them to LAS, builds a LAS dataset,
filters to first returns, and interpolates a DSM raster - then adds it
straight to the active map.

This tool assumes the input is a .txt file containing download URLs for
.laz-format LiDAR tiles, one per line.

Packaged as a toolbox (rather than a standalone script) so it shows up in
ArcGIS Pro's Geoprocessing pane with a proper parameter UI, and can be run
by someone other than the person who wrote it.
"""

import arcpy
import os
import requests


class Toolbox(object):
    """Toolbox definition - labels the toolbox and registers its tool(s)."""
    def __init__(self):
        self.label = "LiDAR Processing Toolbox"
        self.alias = "Lidartool"
        self.tools = [LiDARProcessingDSM]


class LiDARProcessingDSM(object):
    """Downloads LAZ files, decompresses to LAS, builds a DSM, and adds it to the map."""

    def __init__(self):
        self.label = "Download LiDAR and Convert to DSM"
        self.description = "Downloads LAZ files, decompresses to LAS, creates DSM and Adds DSM To Map"

    def getParameterInfo(self):
        """
        Parameters, in order:
          0 - the input .txt file listing LAZ download URLs
          1 - folder where downloaded LAZ files are stored
          2 - folder where decompressed LAS files are stored
          3 - output DSM raster

        Note: in practice all four of these were kept inside the same
        project folder - not strictly required, just what worked cleanly
        for this run.
        """
        param0 = arcpy.Parameter(displayName="Input LiDAR Download List (.txt)", name="download_list", datatype="DEFile", parameterType="Required", direction="Input")
        param1 = arcpy.Parameter(displayName="Folder for Downloaded LAZ", name="laz_folder", datatype="DEFolder", parameterType="Required", direction="Input")
        param2 = arcpy.Parameter(displayName="Folder for LAS", name="las_folder", datatype="DEFolder", parameterType="Required", direction="Input")
        param3 = arcpy.Parameter(displayName="Output DSM Raster", name="dsm_output", datatype="DERasterDataset", parameterType="Required", direction="Output")
        return [param0, param1, param2, param3]

    def execute(self, parameters, messages):
        arcpy.env.overwriteOutput = True

        txt_file = parameters[0].valueAsText
        laz_folder = parameters[1].valueAsText
        las_folder = parameters[2].valueAsText
        output_raster = parameters[3].valueAsText

        # --- Step 1: download LAZ files listed in the input .txt ---
        # Only lines starting with "http" are treated as download URLs, which
        # filters out blank lines or stray text without needing a stricter
        # file format on the input side.
        arcpy.AddMessage("Downloading LAZ files")
        with open(txt_file, "r") as f:
            urls = [line.strip() for line in f if line.strip().lower().startswith('http')]

        for url in urls:
            filename = os.path.basename(url).split('?')[0]
            save_path = os.path.join(laz_folder, filename)
            if not os.path.exists(save_path):
                r = requests.get(url, stream=True)
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        f.write(chunk)

        # --- Step 2: decompress LAZ to LAS ---
        arcpy.AddMessage("Decompressing LAZ files to LAS")
        arcpy.CheckOutExtension("3D")

        arcpy.conversion.ConvertLas(
            laz_folder,
            las_folder,
        )

        # --- Step 3: build a LAS dataset from the decompressed files ---
        arcpy.AddMessage("Creating LAS Dataset from LAS files")
        lasd_path = os.path.join(las_folder, "project_lidar.lasd")

        las_files = [os.path.join(las_folder, f) for f in os.listdir(las_folder) if f.lower().endswith('.las')]

        arcpy.management.CreateLasDataset(
            input=las_files,
            out_las_dataset=lasd_path,
            compute_stats="COMPUTE_STATS"
        )

        # --- Step 4: filter to first returns and interpolate the DSM ---
        # A DSM represents the surface of whatever the laser hit first -
        # treetops, rooftops, ground where nothing was in the way - which is
        # why this filters to first returns (return_values=['1']) rather
        # than last returns, which would approximate bare-earth instead.
        arcpy.AddMessage("Creating DSM Raster")

        lasd_layer = "dsm_filter_layer"
        arcpy.management.MakeLasDatasetLayer(
            in_las_dataset=lasd_path,
            out_layer=lasd_layer,
            return_values=['1']
        )

        # Interpolation type, sampling type, and cell size are left at
        # reasonable defaults here rather than exposed as parameters - a
        # natural next step would be surfacing these so a user could tune
        # vertical resolution and interpolation method without editing code.
        arcpy.conversion.LasDatasetToRaster(
            in_las_dataset=lasd_layer,
            out_raster=output_raster,
            value_field="ELEVATION",
            interpolation_type="BINNING AVERAGE LINEAR",
            sampling_type="CELLSIZE",
            sampling_value=1
        )

        # --- Step 5: add the finished DSM to the active map ---
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        if aprx.activeMap:
            aprx.activeMap.addDataFromPath(output_raster)
            arcpy.AddMessage("DSM added to map!")
            # Symbology isn't set here - left at ArcGIS Pro's default raster
            # stretch, which is a reasonable next thing to add.

        arcpy.CheckInExtension("3D")
