"""Renders a point cloud as a 4-view hologram prism with center focal point."""

import numpy as np
import cv2

# Screen layout: 4 views surrounding a center point
# Top: Front,  Bottom: Back,  Left: Left,  Right: Right
SCREEN_W = 1280
SCREEN_H = 960
VIEW_W = 320
VIEW_H = 240
CENTER_X = SCREEN_W // 2
CENTER_Y = SCREEN_H // 2

# View definitions: (axis_a, axis_b, label, x_offset, y_offset)
# Positioned around center like a prism
_VIEWS = [
    (0, 1, "front",  CENTER_X - VIEW_W // 2, CENTER_Y - VIEW_H - 20),      # Top
    (0, 1, "back",   CENTER_X - VIEW_W // 2, CENTER_Y + 20),               # Bottom
    (1, 2, "left",   CENTER_X - VIEW_W - 20, CENTER_Y - VIEW_H // 2),      # Left
    (0, 2, "right",  CENTER_X + 20,          CENTER_Y - VIEW_H // 2),      # Right
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
    
    # Convert to pixel coordinates (scaled to view size)
    pixels = (normalized * np.array([VIEW_W, VIEW_H])).astype(np.int32)
    
    # Clamp to image bounds
    pixels = np.clip(pixels, 0, [VIEW_W - 1, VIEW_H - 1])
    
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
    Returns a (SCREEN_H, SCREEN_W, 3) uint8 BGR image with 4 views around center prism.
    """
    canvas = np.zeros((SCREEN_H, SCREEN_W, 3), dtype=np.uint8)
    
    try:
        pts = np.asarray(pcd.points)
        if pts.shape[0] == 0:
            return canvas
        
        for axis_a, axis_b, label, x_pos, y_pos in _VIEWS:
            # Project points for this view
            pixels, colors = _project_points(pcd, axis_a, axis_b)
            
            # Draw onto this view's region
            if pixels.shape[0] > 0:
                valid = (pixels[:, 0] >= 0) & (pixels[:, 0] < VIEW_W) & \
                        (pixels[:, 1] >= 0) & (pixels[:, 1] < VIEW_H)
                for i in np.where(valid)[0]:
                    px, py = pixels[i]
                    b, g, r = colors[i]
                    canvas[y_pos + py, x_pos + px] = [b, g, r]
            
            # Draw view border
            cv2.rectangle(canvas, (x_pos, y_pos), (x_pos + VIEW_W, y_pos + VIEW_H), (100, 100, 100), 1)
            # Draw label
            cv2.putText(canvas, label, (x_pos + 5, y_pos + 20),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 100, 100), 1)
        
        # Draw center prism indicator
        prism_size = 30
        cv2.circle(canvas, (CENTER_X, CENTER_Y), prism_size, (255, 100, 100), 2)
        cv2.line(canvas, (CENTER_X - prism_size, CENTER_Y), (CENTER_X + prism_size, CENTER_Y), (255, 100, 100), 1)
        cv2.line(canvas, (CENTER_X, CENTER_Y - prism_size), (CENTER_X, CENTER_Y + prism_size), (255, 100, 100), 1)
    
    except Exception as e:
        print(f"[renderer] error: {e}")
    
    return canvas


def draw_grid(canvas: np.ndarray) -> np.ndarray:
    """Draws crosshairs at the center prism indicator."""
    out = canvas.copy()
    h, w = out.shape[:2]
    
    # Draw center crosshairs
    cv2.line(out, (CENTER_X, 0), (CENTER_X, h), (50, 50, 50), 1)
    cv2.line(out, (0, CENTER_Y), (w, CENTER_Y), (50, 50, 50), 1)
    
    return out
