"""Generate a sample .pkl file for testing replay functionality."""

import numpy as np
import pickle
import sys
from dataclasses import dataclass


@dataclass
class DepthFrame:
    width: int
    height: int
    yaw: float       # radians
    timestamp: float # seconds
    depth: np.ndarray  # shape (height, width), float32, metres


def create_sample_session(output_path: str = "sample_session.pkl", num_frames: int = 30):
    """Generate synthetic depth frames."""
    frames = []
    width, height = 640, 480
    
    for i in range(num_frames):
        # Create synthetic depth data: a simple pattern that changes over time
        # Creates a pyramid-like depth map that rotates
        y, x = np.mgrid[0:height, 0:width]
        
        # Normalize coordinates to -1..1
        y_norm = (y - height / 2) / (height / 2)
        x_norm = (x - width / 2) / (width / 2)
        
        # Add rotation effect based on frame index
        angle = (i / num_frames) * 2 * np.pi
        x_rot = x_norm * np.cos(angle) - y_norm * np.sin(angle)
        y_rot = x_norm * np.sin(angle) + y_norm * np.cos(angle)
        
        # Create depth as distance from center (with some variation)
        depth = np.sqrt(x_rot**2 + y_rot**2) * 2.0 + 0.5  # Range: 0.5 to 2.5 meters
        depth = depth.astype(np.float32)
        
        # Yaw increases linearly over the sequence
        yaw = (i / num_frames) * 2 * np.pi
        
        # Timestamp increases
        timestamp = i * 0.067  # ~15 FPS
        
        frame = DepthFrame(
            width=width,
            height=height,
            yaw=yaw,
            timestamp=timestamp,
            depth=depth
        )
        frames.append(frame)
    
    # Save to pickle
    with open(output_path, "wb") as f:
        pickle.dump(frames, f)
    
    print(f"[create_sample_session] saved {len(frames)} frames → {output_path}")
    print(f"  - Frame size: {width}x{height}")
    print(f"  - Depth range: 0.5 to 2.5 meters")
    print(f"  - Yaw range: 0 to 2π radians")


if __name__ == "__main__":
    output = "sample_session.pkl"
    num_frames = 30
    
    if len(sys.argv) > 1:
        output = sys.argv[1]
    if len(sys.argv) > 2:
        num_frames = int(sys.argv[2])
    
    create_sample_session(output, num_frames)
