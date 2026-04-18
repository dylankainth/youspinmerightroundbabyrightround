"""Renders a point cloud as a 4-quadrant hologram (front/back/left/right)."""

import numpy as np
import open3d as o3d


QUAD_W = 640
QUAD_H = 480
CANVAS_W = QUAD_W * 2
CANVAS_H = QUAD_H * 2

# (azimuth_deg, label) for each quadrant: TL, TR, BL, BR
_VIEWS = [
    (0,   "front"),   # top-left
    (180, "back"),    # top-right
    (270, "left"),    # bottom-left
    (90,  "right"),   # bottom-right
]


def _make_extrinsic(azimuth_deg: float, radius: float = 3.0, elevation: float = 0.3) -> np.ndarray:
    """Camera extrinsic looking at origin from a point on a circle."""
    az = np.radians(azimuth_deg)
    eye = np.array([radius * np.sin(az), elevation, radius * np.cos(az)])
    forward = -eye / np.linalg.norm(eye)
    world_up = np.array([0.0, 1.0, 0.0])
    right = np.cross(forward, world_up)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)

    R = np.stack([right, up, -forward], axis=0)  # (3,3)
    t = -R @ eye
    ext = np.eye(4)
    ext[:3, :3] = R
    ext[:3, 3] = t
    return ext


def render_hologram(pcd: o3d.geometry.PointCloud) -> np.ndarray:
    """
    Returns a (CANVAS_H, CANVAS_W, 3) uint8 BGR image suitable for cv2.imshow.
    Each quadrant is an offscreen render of the cloud from one cardinal direction.
    Requires Open3D ≥ 0.16 for headless OffscreenRenderer.
    """
    canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)

    # Colour all points white for the hologram look
    n = len(pcd.points)
    if n == 0:
        return canvas
    pcd.colors = o3d.utility.Vector3dVector(np.ones((n, 3)))

    intrinsic = o3d.camera.PinholeCameraIntrinsic(
        QUAD_W, QUAD_H,
        fx=500, fy=500,
        cx=QUAD_W / 2, cy=QUAD_H / 2,
    )

    positions = [(0, 0), (QUAD_W, 0), (0, QUAD_H), (QUAD_W, QUAD_H)]

    renderer = o3d.visualization.rendering.OffscreenRenderer(QUAD_W, QUAD_H)
    renderer.scene.set_background([0, 0, 0, 1])  # black

    mat = o3d.visualization.rendering.MaterialRecord()
    mat.shader = "defaultUnlit"
    mat.point_size = 2.0

    renderer.scene.add_geometry("cloud", pcd, mat)

    for (az, label), (ox, oy) in zip(_VIEWS, positions):
        ext = _make_extrinsic(az)
        renderer.setup_camera(intrinsic, ext)
        img = np.asarray(renderer.render_to_image())  # RGB uint8
        bgr = img[:, :, ::-1]
        canvas[oy:oy + QUAD_H, ox:ox + QUAD_W] = bgr

    renderer.scene.remove_geometry("cloud")
    return canvas


def draw_grid(canvas: np.ndarray) -> np.ndarray:
    """Draws cross-hair dividers and labels on the hologram canvas."""
    import cv2
    out = canvas.copy()
    h, w = out.shape[:2]
    mid_x, mid_y = w // 2, h // 2
    cyan = (255, 255, 0)
    cv2.line(out, (mid_x, 0), (mid_x, h), cyan, 1)
    cv2.line(out, (0, mid_y), (w, mid_y), cyan, 1)
    for (_, label), (ox, oy) in zip(_VIEWS, [(0, 0), (mid_x, 0), (0, mid_y), (mid_x, mid_y)]):
        cv2.putText(out, label, (ox + 8, oy + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, cyan, 1, cv2.LINE_AA)
    return out
