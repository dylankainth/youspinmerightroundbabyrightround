"""UDP receiver: unpacks binary depth frames from ESP32."""

import socket
import struct
import numpy as np
from dataclasses import dataclass


HEADER_FMT = ">HHdd"  # width(u16), height(u16), yaw(f64), timestamp(f64)
HEADER_SIZE = struct.calcsize(HEADER_FMT)


@dataclass
class DepthFrame:
    width: int
    height: int
    yaw: float       # radians
    timestamp: float # seconds
    depth: np.ndarray  # shape (height, width), float32, metres


def _unpack_frame(data: bytes) -> DepthFrame:
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Packet too short: {len(data)} bytes")
    width, height, yaw, timestamp = struct.unpack_from(HEADER_FMT, data)
    n_pixels = width * height
    expected = HEADER_SIZE + n_pixels * 4
    if len(data) < expected:
        raise ValueError(f"Expected {expected} bytes, got {len(data)}")
    depth = np.frombuffer(data, dtype=">f4", count=n_pixels, offset=HEADER_SIZE).astype(np.float32)
    return DepthFrame(width=width, height=height, yaw=yaw, timestamp=timestamp,
                      depth=depth.reshape(height, width))


class UDPReceiver:
    def __init__(self, host: str = "0.0.0.0", port: int = 9000, buf: int = 65535):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        self._sock.bind((host, port))
        self._buf = buf
        print(f"[receiver] listening on {host}:{port}")

    def recv(self) -> DepthFrame:
        """Block until one valid frame arrives."""
        while True:
            data, _ = self._sock.recvfrom(self._buf)
            try:
                return _unpack_frame(data)
            except ValueError as e:
                print(f"[receiver] bad packet: {e}")

    def close(self):
        self._sock.close()


# ── replay helpers ────────────────────────────────────────────────────────────

def save_session(frames: list[DepthFrame], path: str):
    import pickle
    with open(path, "wb") as f:
        pickle.dump(frames, f)
    print(f"[receiver] saved {len(frames)} frames → {path}")


def load_session(path: str) -> list[DepthFrame]:
    import pickle
    with open(path, "rb") as f:
        frames = pickle.load(f)
    print(f"[receiver] loaded {len(frames)} frames ← {path}")
    return frames
