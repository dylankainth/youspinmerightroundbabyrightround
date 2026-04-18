"""
Entry point.

Live mode (default):
    python main.py

Record and save:
    python main.py --record session.pkl

Replay a saved session:
    python main.py --replay session.pkl
"""

import argparse
import time
import cv2

from receiver import UDPReceiver, DepthFrame, save_session, load_session
from stitcher import PointCloudStitcher
from renderer import render_hologram, draw_grid

WINDOW = "Hologram"
TARGET_FPS = 15


def _show(canvas, label: str = ""):
    if label:
        import numpy as np
        import cv2 as _cv2
        _cv2.putText(canvas, label, (8, canvas.shape[0] - 10),
                     cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 100, 100), 1)
    cv2.imshow(WINDOW, canvas)


def run_live(record_path: str | None = None):
    rx = UDPReceiver()
    stitcher = PointCloudStitcher()
    recorded: list[DepthFrame] = []
    frame_interval = 1.0 / TARGET_FPS
    last_render = 0.0

    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    print("[main] press Q to quit")

    try:
        while True:
            frame = rx.recv()
            if record_path:
                recorded.append(frame)
            stitcher.add_frame(frame)

            now = time.monotonic()
            if now - last_render >= frame_interval:
                last_render = now
                pcd = stitcher.get_cloud()
                canvas = render_hologram(pcd)
                canvas = draw_grid(canvas)
                pts = len(pcd.points)
                _show(canvas, f"live | pts={pts:,} | yaw={frame.yaw:.2f}rad")
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        rx.close()
        cv2.destroyAllWindows()
        if record_path and recorded:
            save_session(recorded, record_path)


def run_replay(path: str):
    frames = load_session(path)
    if not frames:
        print("[main] no frames to replay")
        return

    stitcher = PointCloudStitcher()
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    print(f"[main] replaying {len(frames)} frames — press Q to quit, SPACE to pause")

    paused = False
    idx = 0
    frame_delay_ms = max(1, int(1000 / TARGET_FPS))

    # Pre-compute real-time deltas
    t0_real = time.monotonic()
    t0_frame = frames[0].timestamp

    while idx < len(frames):
        frame = frames[idx]
        stitcher.add_frame(frame)
        pcd = stitcher.get_cloud()
        canvas = render_hologram(pcd)
        canvas = draw_grid(canvas)
        pts = len(pcd.points)
        _show(canvas, f"replay {idx+1}/{len(frames)} | pts={pts:,} | yaw={frame.yaw:.2f}rad")

        key = cv2.waitKey(frame_delay_ms) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" "):
            paused = not paused
        if not paused:
            idx += 1

    cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description="ESP32 hologram viewer")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--record", metavar="FILE",
                       help="live mode — also save frames to FILE")
    group.add_argument("--replay", metavar="FILE",
                       help="replay a previously recorded session")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()

    if args.replay:
        run_replay(args.replay)
    else:
        run_live(record_path=args.record)


if __name__ == "__main__":
    main()
