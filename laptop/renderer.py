"""Renders a point cloud as a 4-quadrant hologram (front/back/left/right)."""

import numpy as np
import cv2

QUAD_W = 640
QUAD_H = 480
CANVAS_W = QUAD_W * 2
CANVAS_H = QUAD_H * 2

# View definitions: (axis_a, axis_b, label)
# Project onto different planes for different views
_VIEWS = [
    (0, 1, "front"),    # X-Y plane (front view)
    (0, 1, "back"),     # X-Y plane (back view) 
    (1, 2, "left"),     # Y-Z plane (left view)
    (0, 2, "right"),    # X-Z plane (right view)
]

# Scale for normalizing coordinates
SCALE = 2.0  # meters to pixels scale factor


def _project_points(pcd, axis_a: int, axis_b: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Project 3D points onto a 2D plane.
    Returns (2D positions in pixels, colors for each point).
    """
    pts = np.asarray(pcd.points)
    if pts.shape[0] == 0:
        return np.empty((0, 2), dtype=np.int32), np.empty((0, 3), dtype=np.uint8)
    
    # Get the two axes we're projecting onto
    proj = pts[:, [axis_a, axis_b]]
    
    # Normalize to image space
    # Assume points are roughly in -2..2 meters range
    normalized = (proj / SCALE + 1.0) * 0.5  # Map to 0..1
    
    # Convert to pixel coordinates
    pixels = (normalized * np.array([QUAD_W, QUAD_H])).astype(np.int32)
    
    # Clamp to image bounds
    pixels = np.clip(pixels, 0, [QUAD_W - 1, QUAD_H - 1])
    
    # Color by Z height (use third axis not projected)
    z_axis = 2 if axis_a != 2 and axis_b != 2 else (0 if axis_a != 0 else 1)
    z = pts[:, z_axis]
    z_min, z_max = z.min(), z.max()
    z_norm = (z - z_min) / (z_max - z_min + 1e-6)
    
    # Plasma colormap (simple approximation)
    colors = np.zeros((pts.shape[0], 3), dtype=np.uint8)
    colors[:, 0] = (z_norm * 255).astype(np.uint8)  # R
    colors[:, 1] = (np.sin(z_norm * np.pi) * 255).astype(np.uint8)  # G
    colors[:, 2] = ((1 - z_norm) * 255).astype(np.uint8)  # B
    
    return pixels, colors


def render_hologram(pcd) -> np.ndarray:
    """
    Returns a (CANVAS_H, CANVAS_W, 3) uint8 BGR image.
    Four views arranged in a 2x2 grid on black background.
    """
    canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
    
    try:
        pts = np.asarray(pcd.points)
        if pts.shape[0] == 0:
            return canvas
        
        quad_positions = [(0, 0), (QUAD_W, 0), (0, QUAD_H), (QUAD_W, QUAD_H)]
        
        for (axis_a, axis_b, _label), (ox, oy) in zip(_VIEWS, quad_positions):
            # Project points for this view
            pixels, colors = _project_points(pcd, axis_a, axis_b)
            
            # Draw onto this quad
            if pixels.shape[0] > 0:
                valid = (pixels[:, 0] >= 0) & (pixels[:, 0] < QUAD_W) & \
                        (pixels[:, 1] >= 0) & (pixels[:, 1] < QUAD_H)
                for i in np.where(valid)[0]:
                    x, y = pixels[i]
                    b, g, r = colors[i]
                    canvas[oy + y, ox + x] = [b, g, r]
    
    except Exception as e:
        print(f"[renderer] error: {e}")
    
    return canvas


def draw_grid(canvas: np.ndarray) -> np.ndarray:
    """Draws cross-hair dividers and labels on the hologram canvas."""
    out = canvas.copy()
    h, w = out.shape[:2]
    mid_x, mid_y = w // 2, h // 2
    cyan = (255, 255, 0)
    cv2.line(out, (mid_x, 0), (mid_x, h), cyan, 1)
    cv2.line(out, (0, mid_y), (w, mid_y), cyan, 1)
    
    labels = ["front", "back", "left", "right"]
    positions = [(0, 0), (mid_x, 0), (0, mid_y), (mid_x, mid_y)]
    
    for label, (ox, oy) in zip(labels, positions):
        cv2.putText(out, label, (ox + 8, oy + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, cyan, 1, cv2.LINE_AA)
    
    return out
