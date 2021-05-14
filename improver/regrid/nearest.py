# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# (C) British Crown Copyright 2017-2021 Met Office.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
"""
Nearest neighbour interpolation functions
"""

import numpy as np

from improver.regrid.grid import similar_surface_classify
from improver.regrid.idw import nearest_input_pts


def nearest_with_mask_regrid(
    distances,
    indexes,
    surface_type_mask,
    in_latlons,
    out_latlons,
    in_classified,
    out_classified,
    vicinity,
):
    """
    Main regridding function for the nearest distance option
    some input just for handling island-like points

    Args:
        distances(numpy.ndarray):
            distnace array from each target grid point to its source grid points
        indexes(numpy.ndarray):
            array of source grid point number for each target grid points
        surface_type_mask(numpy.ndarray):
            numpy ndarray of bool, true if source points' surface type matches target point's
        in_latlons(numpy.ndarray):
            tource points's latitude-longitudes
        out_latlons(numpy.ndarray):
            target points's latitude-longitudes
        in_classified(numpy.ndarray):
            land_sea type for source grid points (land =>True)
        out_classified(numpy.ndarray):
            land_sea type for terget grid points (land =>True)
        vicinity (float32):
            radius of specified searching domain (unit: m)

    Return:
        Tuple[numpy.ndarray, numpy.ndarray]:
             distances: updated distnace array from each target grid point to its source grid points
             indexes: updated array of four source grid point number for each target grid points
 
    """

    # Check if there are output points with mismatched surface types
    matched_nearby_points_count = np.count_nonzero(surface_type_mask, axis=1)
    points_with_mismatches = (np.where(matched_nearby_points_count < 4))[0]
    # Look for nearest input points for the output points with mismatched surface
    indexes, distances, surface_type_mask = update_nearest_points(
        points_with_mismatches,
        in_latlons,
        out_latlons,
        indexes,
        distances,
        surface_type_mask,
        in_classified,
        out_classified,
    )

    # Handle island and lake like output points - find more distant same surface type input points
    # Note: surface_type_mask has been updated above
    matched_nearby_points_count = np.count_nonzero(surface_type_mask, axis=1)
    fully_mismatched_points = (np.where(matched_nearby_points_count == 0))[0]

    if fully_mismatched_points.shape[0] > 0:
        indexes, surface_type_mask = lakes_islands(
            fully_mismatched_points,
            indexes,
            surface_type_mask,
            in_latlons,
            out_latlons,
            in_classified,
            out_classified,
            vicinity,
        )

    # Convert mask to be true where input points should not be considered
    inverse_surface_mask = np.logical_not(surface_type_mask)

    # Replace distances with infinity where they should not be used
    masked_distances = np.where(inverse_surface_mask, np.float64(np.inf), distances)

    # Distances and indexes have been prepared to handle the mask, so can now
    # call the non-masked regrid function in process
    return masked_distances, indexes


def nearest_regrid(distances, indexes, in_values):
    """
    Main regridding function for the nearest distance option

    Args:
        distances(numpy.ndarray):
            distnace array from each target grid point to its source grid points
        indexes(numpy.ndarray):
            array of source grid point number for each target grid points
        in_values(numpy.ndarray):
            input values (multidimensional, reshaped in function _reshape_data_cube)

    Returns:
        numpy.ndarray: output values (multidimensional)
    """
    min_index = np.argmin(distances, axis=1)
    index0 = np.arange(min_index.shape[0])
    index_in = indexes[index0, min_index]
    output = in_values[index_in]
    return output


def update_nearest_points(
    points_with_mismatches,
    in_latlons,
    out_latlons,
    indexes,
    distances,
    surface_type_mask,
    in_classified,
    out_classified,
):
    """
    updating nearest source points and distances/surface_type for selective target points

    Args:
        points_with_mismatches(numpy.ndarray):
            selected target points which will use Inverse Distance Weighting(idw) approach
        in_latlons(numpy.ndarray):
            Source points's latitude-longitudes
        out_latlons(numpy.ndarray):
            Target points's latitude-longitudes
        indexes(numpy.ndarray):
            array of source grid point number for all target grid points
        distances(numpy.ndarray):
            distnace array from each target grid point to its source grid points
        surface_type_mask(numpy.ndarray)):
            numpy ndarray of bool, true if source point type matches target point type
        in_classified(numpy.ndarray):
            land_sea type for source grid points (land =>True)
        out_classified(numpy.ndarray):
            land_sea type for terget grid points (land =>True)

    Returns:
        Tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray]:
            updated Indexes - source grid point number for all target grid points.
            updated surface_type_mask - matching info between source/target point types
            updated distnace - array from each target grid point to its source grid points
    """
    # Gather output points with mismatched surface type and find four nearest input
    # points via KDtree
    out_latlons_with_mismatches = out_latlons[points_with_mismatches]
    k_nearest = 4
    distances_updates, indexes_updates = nearest_input_pts(
        in_latlons, out_latlons_with_mismatches, k_nearest
    )
    # Calculate update to surface classification at mismatched points
    out_classified_with_mismatches = out_classified[points_with_mismatches]
    surface_type_mask_updates = similar_surface_classify(
        in_classified, out_classified_with_mismatches, indexes_updates
    )
    # Apply updates to indexes, distances and surface type mask
    indexes[points_with_mismatches] = indexes_updates
    distances[points_with_mismatches] = distances_updates
    surface_type_mask[points_with_mismatches] = surface_type_mask_updates
    return indexes, distances, surface_type_mask


def lakes_islands(
    lake_island_indexes,
    indexes,
    surface_type_mask,
    in_latlons,
    out_latlons,
    in_classified,
    out_classified,
    vicinity,
):
    """
    updating source points and weighting for 4-unmatching-source-point cases
    this function searching nearest 8 points to check if any matching point exists
    Note that a similar function can be found in bilinear.py for bilinear
    regridding rather than nearest neighbour regridding.

    Args:
        lake_island_indexes (numpy.ndarray):
            indexes of points which are lakes/islands surrounded by mismatched surface type
        in_latlons (numpy.ndarray):
            tource points's latitude-longitudes
        out_latlons (numpy.ndarray):
            target points's latitude-longitudes
        surface_type_mask (numpy.ndarray)):
            numpy ndarray of bool, true if source point type matches target point type
        indexes (numpy.ndarray):
            array of source grid point number for all target grid points
        in_classified (numpy.ndarray):
            land_sea type for source grid points (land =>True)
        out_classified (numpy.ndarray):
            land_sea type for target grid points (land =>True)
        vicinity (float):
            Radius of vicinity to search for a matching surface type, in metres

    Returns:
        Tuple[numpy.ndarray, numpy.ndarray]:
            updated Indexes - source grid point number for all target grid points.
            updated surface_type_mask - matching info between source/target point types
    """

    out_latlons_updates = out_latlons[lake_island_indexes]

    # Consider a larger area of 8 nearest points to look for more distant same
    # surface type input points.
    # more than 8 points are within searching limits not considered here
    k_nearest = 8
    distances_updates, indexes_updates = nearest_input_pts(
        in_latlons, out_latlons_updates, k_nearest
    )
    # Update output surface classification and surface type mask
    out_classified_updates = out_classified[lake_island_indexes]
    surface_type_mask_updates = similar_surface_classify(
        in_classified, out_classified_updates, indexes_updates
    )

    # Where distance is outside specified vicinity, set surface type to be mismatched
    # so that it will not be used, update surface type mask again
    distance_not_in_vicinity = distances_updates > vicinity
    surface_type_mask_updates = np.where(
        distance_not_in_vicinity, False, surface_type_mask_updates
    )

    count_matching_surface = np.count_nonzero(surface_type_mask_updates, axis=1)
    points_with_no_match = (np.where(count_matching_surface == 0))[0]
    if points_with_no_match.shape[0] > 0:
        # No improved input point has been found with the increase to 8 nearest points
        # Take the original nearest point, disregard the surface type
        no_match_indexes = lake_island_indexes[points_with_no_match]
        surface_type_mask[no_match_indexes, :] = True

    # From the expansion to 8 nearby input points, a same surface type input has been found
    # Update the index and surface type mask to use the newly found same surface type input point
    points_with_match = (np.where(count_matching_surface > 0))[0]
    # pylint: disable=unsubscriptable-object
    count_of_points_with_match = points_with_match.shape[0]

    for point_idx in range(count_of_points_with_match):
        # Reset all input surface types to mismatched
        match_indexes = lake_island_indexes[points_with_match[point_idx]]
        surface_type_mask[match_indexes, :] = False
        # Loop through 8 nearest points found
        for i in range(k_nearest):
            # Look for an input point with same surface type as output
            if surface_type_mask_updates[points_with_match[point_idx], i]:
                # When found, update the indexes and surface mask to use that improved input point
                indexes[match_indexes, 0] = indexes_updates[
                    points_with_match[point_idx], i
                ]
                surface_type_mask[match_indexes, 0] = True
                break

    return indexes, surface_type_mask
