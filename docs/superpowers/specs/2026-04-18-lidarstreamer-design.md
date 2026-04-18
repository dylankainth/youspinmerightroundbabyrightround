# LidarStreamer iOS App — Design Spec

## Overview

LidarStreamer is a minimal iOS app that captures LiDAR depth frames via ARKit, reads device yaw from CoreMotion, and streams downsampled depth + yaw + timestamp as binary UDP packets to a laptop receiver. It replaces the ESP32 as the depth source in the existing hologram pipeline.

## Architecture

**Approach:** ViewController + UDPStreamer helper (UIKit, programmatic UI).

| File | Action | Purpose |
|---|---|---|
| `ViewController.swift` | Edit | ARKit session, CoreMotion, UI, orchestration |
| `UDPStreamer.swift` | Create | UDP socket, packet encoding, Bonjour browse |
| `Info.plist` | Edit | Privacy descriptions, device capabilities |
| `AppDelegate.swift` | Minimal edit | Keep screen awake during streaming |

## Packet Format (Wire Protocol)

Must be byte-compatible with `laptop/receiver.py` (`HEADER_FMT = ">HHdd"`).

```
Header (20 bytes, big-endian):
  [0..1]   UInt16  — width  (always 64)
  [2..3]   UInt16  — height (always 48)
  [4..11]  Float64 — yaw in radians
  [12..19] Float64 — timestamp in seconds (epoch)

Body (12,288 bytes):
  64x48 Float32 values, big-endian — depth in metres

Total: 12,308 bytes per packet
```

Fits in a single UDP datagram. No chunking required.

### Downsampling

ARKit native depth: 256x192 Float32 (`kCVPixelFormatType_DepthFloat32`).
Target: 64x48. Reduction: 4x on each axis via strided sampling (`depth[row * 4][col * 4]`).

## ARKit & Motion Pipeline

### ARSession

- `ARWorldTrackingConfiguration` with `.sceneDepth` frame semantic
- No AR view rendered — bare `ARSession`, frames received via `session(_:didUpdate:)` delegate
- Process every 6th frame (~10fps from ~60fps source)

### CMDeviceMotion

- `CMMotionManager` at 50Hz (`updateInterval = 0.02`)
- Read `attitude.yaw` from latest sample at frame-packaging time
- Yaw is in radians — matches receiver.py expectation

### Frame Processing (every 6th AR frame)

1. Guard `frame.sceneDepth?.depthMap` exists
2. Lock pixel buffer, stride-sample 4x on each axis -> 64x48 Float32 array
3. Read `motionManager.deviceMotion.attitude.yaw`
4. Convert `frame.timestamp` (seconds since boot) to epoch time
5. Call `UDPStreamer.send(depth:yaw:timestamp:)`

### Threading

- ARSession delegate fires on a serial session queue
- Motion reads latest cached value (CMMotionManager internally synchronized)
- UDP `sendto()` is non-blocking on DGRAM socket — runs inline on AR delegate queue

## UDPStreamer

### Responsibilities

- Owns a POSIX UDP socket (`socket(AF_INET, SOCK_DGRAM, 0)`)
- Encodes packets in the wire format above
- Browses for Bonjour services for auto-discovery
- Reports connection state via callback

### Socket Lifecycle

- Created on `start(host:port:)`, closed on `stop()`
- Non-blocking `sendto()` — fire and forget
- No receive path on iOS side

### Bonjour Discovery

- `NWBrowser` (Network.framework) browsing for `_lidarstream._udp.`
- On result found: resolve to IP:port, auto-populate UI text field
- Fallback: user types IP manually if Bonjour finds nothing
- Note: the Python receiver does not yet advertise this service — a small `zeroconf` addition to `receiver.py` is needed separately for auto-discovery to work. Until then, manual IP entry is the primary flow.

### Packet Encoding

```swift
func send(depth: [Float32], yaw: Double, timestamp: Double)
```

Builds a `Data` buffer: big-endian UInt16 width/height, big-endian Float64 yaw/timestamp, big-endian Float32 depth values. Calls `sendto()`.

### State

Enum: `.idle`, `.streaming`, `.error(String)`. ViewController observes to update UI.

## UI

Programmatic UIKit, dark background. No storyboard.

### Layout

- **Top:** IP text field (pre-filled from Bonjour or default), port text field (default 9000), Start/Stop button
- **Middle:** Three status labels:
  - Status: "Idle" / "Streaming to 192.168.1.50:9000" / "Error: ..."
  - FPS: "TX: 9.8 fps"
  - Yaw: "Yaw: 1.42 rad (81.4 deg)"
- No AR camera preview — saves GPU/memory

### FPS Calculation

Ring buffer of last 10 send timestamps. FPS = count / (newest - oldest).

## Info.plist

- `NSCameraUsageDescription` — required for ARKit
- `NSMotionUsageDescription` — required for CMDeviceMotion
- `UIRequiredDeviceCapabilities` — add `arkit`

## Error Handling & Edge Cases

### ARKit

- Check `ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth)` before starting; alert if no LiDAR
- Handle `session(_:didFailWithError:)` — update status, stop streaming
- Skip frames where `sceneDepth` is nil (frame counter still increments)

### Network

- `sendto()` failures are silent (UDP fire-and-forget)
- `ENETUNREACH` or similar — update status to error; next frame retries naturally
- No retry/backoff logic

### Motion

- Skip frame if `deviceMotion` is nil (first sample hasn't arrived)
- CMMotionManager created once, never recreated

### App Lifecycle

- Pause ARSession and motion on `viewWillDisappear` / app background
- Resume on `viewWillAppear` / app foreground
- `UIApplication.shared.isIdleTimerDisabled = true` during streaming
