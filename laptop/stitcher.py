"""Converts depth frames to 3-D points and accumulates a rotating point cloud."""

import numpy as np
import open3d as o3d
from receiver import DepthFrame


# Intrinsics — adjust to match your sensor
FX = 100.0  # focal length x (pixels)
FY = 100.0  # focal length y (pixels)
# Principal point is derived from frame dimensions at runtime.

# Depth validity range (metres)
DEPTH_MIN = 0.05
DEPTH_MAX = 10.0

# Rolling buffer: keep at most this many frames to bound memory
MAX_FRAMES = 500


def depth_to_points(frame: DepthFrame) -> np.ndarray:
    """
    Back-project a depth image to a (N,3) float32 XYZ array in camera space.
    Invalid/out-of-range depths are excluded.
    """
    h, w = frame.depth.shape
    cx, cy = w / 2.0, h / 2.0

    us = np.arange(w, dtype=np.float32)
    vs = np.arange(h, dtype=np.float32)
    ug, vg = np.meshgrid(us, vs)

    d = frame.depth  # (H,W)
    valid = (d > DEPTH_MIN) & (d < DEPTH_MAX)

    d_v = d[valid]
    x = (ug[valid] - cx) * d_v / FX
    y = (vg[valid] - cy) * d_v / FY
    z = d_v
    return np.column_stack([x, y, z])  # camera coords: +Z forward


def _rotation_y(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array([[ c, 0, s],
                     [ 0, 1, 0],
                     [-s, 0, c]], dtype=np.float64)


class PointCloudStitcher:
    def __init__(self, voxel_size: float = 0.02):
        self._voxel_size = voxel_size
        self._accumulated: list[np.ndarray] = []  # list of (N,3) arrays

    def add_frame(self, frame: DepthFrame):
        pts = depth_to_points(frame)
        if pts.size == 0:
            return
        # Rotate into world space using yaw
        R = _rotation_y(frame.yaw)
        pts_world = (R @ pts.T).T
        self._accumulated.append(pts_world.astype(np.float32))
        # Evict oldest frames beyond rolling buffer
        if len(self._accumulated) > MAX_FRAMES:
            self._accumulated.pop(0)

    def get_cloud(self) -> o3d.geometry.PointCloud:
        if not self._accumulated:
            return o3d.geometry.PointCloud()
        all_pts = np.concatenate(self._accumulated, axis=0)
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(all_pts)
        if self._voxel_size > 0:
            pcd = pcd.voxel_down_sample(self._voxel_size)
        return pcd

    def reset(self):
        self._accumulated.clear()
