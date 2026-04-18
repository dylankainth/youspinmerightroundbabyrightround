# LidarStreamer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an iOS app that streams LiDAR depth frames + yaw over wireless UDP to the existing Python hologram receiver.

**Architecture:** UIKit app with two main files — `ViewController.swift` (ARKit, CoreMotion, UI orchestration) and `UDPStreamer.swift` (POSIX UDP socket, binary packet encoding, Bonjour browsing). No storyboard; programmatic UI. Packets match the existing `laptop/receiver.py` wire format exactly (`">HHdd"` header + big-endian float32 depth body).

**Tech Stack:** Swift, UIKit, ARKit, CoreMotion, Network.framework (NWBrowser for Bonjour), POSIX sockets (sendto), iOS 17+

**Spec:** `docs/superpowers/specs/2026-04-18-lidarstreamer-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `ios/LidarStreamer.xcodeproj` | Create | Xcode project (created via `xcodebuild` or Xcode) |
| `ios/LidarStreamer/AppDelegate.swift` | Create | App entry point, idle timer disable |
| `ios/LidarStreamer/UDPStreamer.swift` | Create | UDP socket, packet encoding, Bonjour browse |
| `ios/LidarStreamer/ViewController.swift` | Create | ARKit session, CoreMotion, UI, orchestration |
| `ios/LidarStreamer/Info.plist` | Create | Privacy descriptions, device capabilities |

All iOS files live under `ios/` to parallel the existing `laptop/` and `esp32/` directories.

---

## Task 0: Create Xcode Project Skeleton

**Files:**
- Create: `ios/LidarStreamer.xcodeproj/project.pbxproj`
- Create: `ios/LidarStreamer/AppDelegate.swift`
- Create: `ios/LidarStreamer/ViewController.swift`
- Create: `ios/LidarStreamer/Info.plist`

- [ ] **Step 1: Create project directory**

```bash
mkdir -p ios/LidarStreamer
```

- [ ] **Step 2: Create Info.plist**

Create `ios/LidarStreamer/Info.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>$(EXECUTABLE_NAME)</string>
    <key>CFBundleIdentifier</key>
    <string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>$(PRODUCT_NAME)</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSRequiresIPhoneOS</key>
    <true/>
    <key>UILaunchStoryboardName</key>
    <string>LaunchScreen</string>
    <key>UIRequiredDeviceCapabilities</key>
    <array>
        <string>armv7</string>
        <string>arkit</string>
    </array>
    <key>UISupportedInterfaceOrientations</key>
    <array>
        <string>UIInterfaceOrientationPortrait</string>
    </array>
    <key>NSCameraUsageDescription</key>
    <string>LidarStreamer uses the camera for ARKit LiDAR depth capture.</string>
    <key>NSMotionUsageDescription</key>
    <string>LidarStreamer reads device motion to track yaw orientation.</string>
    <key>NSLocalNetworkUsageDescription</key>
    <string>LidarStreamer sends depth data over the local network.</string>
    <key>NSBonjourServices</key>
    <array>
        <string>_lidarstream._udp.</string>
    </array>
</dict>
</plist>
```

- [ ] **Step 3: Create minimal AppDelegate.swift**

Create `ios/LidarStreamer/AppDelegate.swift`:

```swift
import UIKit

@main
class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        window = UIWindow(frame: UIScreen.main.bounds)
        window?.rootViewController = ViewController()
        window?.makeKeyAndVisible()
        return true
    }
}
```

- [ ] **Step 4: Create stub ViewController.swift**

Create `ios/LidarStreamer/ViewController.swift`:

```swift
import UIKit

class ViewController: UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
    }
}
```

- [ ] **Step 5: Create the Xcode project via `xcodegen` or manually**

Since generating a `.pbxproj` by hand is fragile, the recommended approach is:

Option A — If `xcodegen` is installed:
Create `ios/project.yml`:
```yaml
name: LidarStreamer
targets:
  LidarStreamer:
    type: application
    platform: iOS
    deploymentTarget: "17.0"
    sources:
      - path: LidarStreamer
    settings:
      INFOPLIST_FILE: LidarStreamer/Info.plist
      PRODUCT_BUNDLE_IDENTIFIER: com.starkhacks.lidarstreamer
      DEVELOPMENT_TEAM: ""
      SWIFT_VERSION: "5.0"
      TARGETED_DEVICE_FAMILY: "1"
    dependencies: []
```

```bash
cd ios && xcodegen generate
```

Option B — Open Xcode, create a new iOS App project named "LidarStreamer" in `ios/`, delete the auto-generated files, and replace with ours.

- [ ] **Step 6: Commit**

```bash
git add ios/
git commit -m "feat(ios): scaffold LidarStreamer Xcode project"
```

---

## Task 1: UDPStreamer — Packet Encoding

**Files:**
- Create: `ios/LidarStreamer/UDPStreamer.swift`

This task builds the packet encoding and socket send logic. No Bonjour yet.

- [ ] **Step 1: Create UDPStreamer.swift with state enum and packet builder**

Create `ios/LidarStreamer/UDPStreamer.swift`:

```swift
import Foundation

enum StreamerState: Equatable {
    case idle
    case streaming
    case error(String)
}

final class UDPStreamer {

    private(set) var state: StreamerState = .idle
    var onStateChange: ((StreamerState) -> Void)?

    private var fd: Int32 = -1
    private var dest = sockaddr_in()

    private let outputWidth: UInt16 = 64
    private let outputHeight: UInt16 = 48

    // MARK: - Lifecycle

    func start(host: String, port: UInt16) {
        stop()

        fd = socket(AF_INET, SOCK_DGRAM, 0)
        guard fd >= 0 else {
            setState(.error("socket() failed: \(errno)"))
            return
        }

        dest = sockaddr_in()
        dest.sin_family = sa_family_t(AF_INET)
        dest.sin_port = port.bigEndian
        guard host.withCString({ inet_pton(AF_INET, $0, &dest.sin_addr) }) == 1 else {
            setState(.error("Invalid IP: \(host)"))
            close(fd)
            fd = -1
            return
        }

        setState(.streaming)
    }

    func stop() {
        if fd >= 0 {
            Darwin.close(fd)
            fd = -1
        }
        setState(.idle)
    }

    // MARK: - Send

    func send(depth: UnsafePointer<Float32>, yaw: Double, timestamp: Double) {
        guard fd >= 0 else { return }

        let pixelCount = Int(outputWidth) * Int(outputHeight)
        let headerSize = 2 + 2 + 8 + 8  // UInt16 + UInt16 + Float64 + Float64
        let bodySize = pixelCount * 4
        let totalSize = headerSize + bodySize

        var data = Data(capacity: totalSize)

        // Header — all big-endian
        var w = outputWidth.bigEndian
        var h = outputHeight.bigEndian
        var y = yaw.bitPattern.bigEndian
        var t = timestamp.bitPattern.bigEndian
        data.append(UnsafeBufferPointer(start: &w, count: 1))
        data.append(UnsafeBufferPointer(start: &h, count: 1))
        data.append(UnsafeBufferPointer(start: &y, count: 1))
        data.append(UnsafeBufferPointer(start: &t, count: 1))

        // Body — big-endian Float32
        for i in 0..<pixelCount {
            var val = depth[i].bitPattern.bigEndian
            data.append(UnsafeBufferPointer(start: &val, count: 1))
        }

        // Send
        let result = data.withUnsafeBytes { buf in
            withUnsafePointer(to: dest) { addr in
                addr.withMemoryRebound(to: sockaddr.self, capacity: 1) { sa in
                    sendto(fd, buf.baseAddress, totalSize, 0, sa, socklen_t(MemoryLayout<sockaddr_in>.size))
                }
            }
        }

        if result < 0 {
            let code = errno
            if code == ENETUNREACH || code == EHOSTUNREACH {
                setState(.error("Network unreachable"))
            }
        }
    }

    // MARK: - Private

    private func setState(_ newState: StreamerState) {
        guard state != newState else { return }
        state = newState
        onStateChange?(newState)
    }
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd ios && xcodebuild -project LidarStreamer.xcodeproj -scheme LidarStreamer -destination 'generic/platform=iOS' build 2>&1 | tail -5
```

Expected: `BUILD SUCCEEDED`

- [ ] **Step 3: Commit**

```bash
git add ios/LidarStreamer/UDPStreamer.swift
git commit -m "feat(ios): add UDPStreamer with packet encoding and UDP send"
```

---

## Task 2: UDPStreamer — Bonjour Discovery

**Files:**
- Modify: `ios/LidarStreamer/UDPStreamer.swift`

- [ ] **Step 1: Add Bonjour browsing via NWBrowser**

Add these imports and the Bonjour extension to `UDPStreamer.swift`:

At the top, add:
```swift
import Network
```

Add a new section to the `UDPStreamer` class:

```swift
    // MARK: - Bonjour

    private var browser: NWBrowser?
    var onBonjourDiscovered: ((_ host: String, _ port: UInt16) -> Void)?

    func startBrowsing() {
        let descriptor = NWBrowser.Descriptor.bonjour(type: "_lidarstream._udp.", domain: nil)
        let browser = NWBrowser(for: descriptor, using: .udp)

        browser.stateUpdateHandler = { state in
            if case .failed(let err) = state {
                print("[Bonjour] browse failed: \(err)")
            }
        }

        browser.browseResultsChangedHandler = { [weak self] results, _ in
            guard let result = results.first else { return }
            if case .service(let name, let type, let domain, _) = result.endpoint {
                self?.resolveService(name: name, type: type, domain: domain)
            }
        }

        browser.start(queue: .main)
        self.browser = browser
    }

    func stopBrowsing() {
        browser?.cancel()
        browser = nil
    }

    private func resolveService(name: String, type: String, domain: String) {
        let endpoint = NWEndpoint.service(name: name, type: type, domain: domain, interface: nil)
        let params = NWParameters.udp
        let connection = NWConnection(to: endpoint, using: params)

        connection.stateUpdateHandler = { [weak self] state in
            if case .ready = state {
                if let innerEndpoint = connection.currentPath?.remoteEndpoint,
                   case .hostPort(let host, let port) = innerEndpoint {
                    let hostStr: String
                    switch host {
                    case .ipv4(let addr):
                        hostStr = "\(addr)"
                    case .ipv6(let addr):
                        hostStr = "\(addr)"
                    case .name(let name, _):
                        hostStr = name
                    @unknown default:
                        hostStr = "\(host)"
                    }
                    let portNum = port.rawValue
                    DispatchQueue.main.async {
                        self?.onBonjourDiscovered?(hostStr, portNum)
                    }
                }
                connection.cancel()
            }
        }

        connection.start(queue: .global(qos: .utility))
    }
```

- [ ] **Step 2: Verify it compiles**

```bash
cd ios && xcodebuild -project LidarStreamer.xcodeproj -scheme LidarStreamer -destination 'generic/platform=iOS' build 2>&1 | tail -5
```

Expected: `BUILD SUCCEEDED`

- [ ] **Step 3: Commit**

```bash
git add ios/LidarStreamer/UDPStreamer.swift
git commit -m "feat(ios): add Bonjour discovery to UDPStreamer"
```

---

## Task 3: ViewController — UI Layout

**Files:**
- Modify: `ios/LidarStreamer/ViewController.swift`

This task builds the programmatic UI with all controls and labels. No ARKit/Motion yet.

- [ ] **Step 1: Replace ViewController.swift with full UI layout**

Replace the contents of `ios/LidarStreamer/ViewController.swift`:

```swift
import UIKit
import ARKit
import CoreMotion

class ViewController: UIViewController {

    // MARK: - UI Elements

    private let ipField: UITextField = {
        let tf = UITextField()
        tf.text = "192.168.1."
        tf.placeholder = "Receiver IP"
        tf.borderStyle = .roundedRect
        tf.keyboardType = .decimalPad
        tf.backgroundColor = .secondarySystemBackground
        tf.textColor = .white
        tf.translatesAutoresizingMaskIntoConstraints = false
        return tf
    }()

    private let portField: UITextField = {
        let tf = UITextField()
        tf.text = "9000"
        tf.placeholder = "Port"
        tf.borderStyle = .roundedRect
        tf.keyboardType = .numberPad
        tf.backgroundColor = .secondarySystemBackground
        tf.textColor = .white
        tf.translatesAutoresizingMaskIntoConstraints = false
        tf.widthAnchor.constraint(equalToConstant: 80).isActive = true
        return tf
    }()

    private let toggleButton: UIButton = {
        let btn = UIButton(type: .system)
        btn.setTitle("Start", for: .normal)
        btn.titleLabel?.font = .boldSystemFont(ofSize: 18)
        btn.translatesAutoresizingMaskIntoConstraints = false
        return btn
    }()

    private let statusLabel = ViewController.makeLabel("Status: Idle")
    private let fpsLabel = ViewController.makeLabel("TX: — fps")
    private let yawLabel = ViewController.makeLabel("Yaw: — rad (—°)")

    private static func makeLabel(_ text: String) -> UILabel {
        let l = UILabel()
        l.text = text
        l.textColor = .systemGreen
        l.font = .monospacedSystemFont(ofSize: 16, weight: .regular)
        l.translatesAutoresizingMaskIntoConstraints = false
        return l
    }

    // MARK: - State

    private let streamer = UDPStreamer()
    private var isStreaming = false

    // MARK: - Lifecycle

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        layoutUI()
        toggleButton.addTarget(self, action: #selector(toggleTapped), for: .touchUpInside)

        streamer.onStateChange = { [weak self] state in
            DispatchQueue.main.async { self?.updateStatusUI(state) }
        }

        streamer.onBonjourDiscovered = { [weak self] host, port in
            self?.ipField.text = host
            self?.portField.text = "\(port)"
            self?.statusLabel.text = "Status: Discovered \(host):\(port)"
        }

        streamer.startBrowsing()
    }

    // MARK: - Layout

    private func layoutUI() {
        let ipPortStack = UIStackView(arrangedSubviews: [ipField, portField])
        ipPortStack.axis = .horizontal
        ipPortStack.spacing = 8
        ipPortStack.translatesAutoresizingMaskIntoConstraints = false

        let infoStack = UIStackView(arrangedSubviews: [statusLabel, fpsLabel, yawLabel])
        infoStack.axis = .vertical
        infoStack.spacing = 12
        infoStack.translatesAutoresizingMaskIntoConstraints = false

        let mainStack = UIStackView(arrangedSubviews: [ipPortStack, toggleButton, infoStack])
        mainStack.axis = .vertical
        mainStack.spacing = 24
        mainStack.alignment = .center
        mainStack.translatesAutoresizingMaskIntoConstraints = false

        view.addSubview(mainStack)
        NSLayoutConstraint.activate([
            mainStack.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            mainStack.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 40),
            ipPortStack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 20),
            ipPortStack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -20),
            infoStack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 20),
        ])
    }

    // MARK: - Actions

    @objc private func toggleTapped() {
        // Will be wired to ARKit/Motion in next task
    }

    private func updateStatusUI(_ state: StreamerState) {
        switch state {
        case .idle:
            statusLabel.text = "Status: Idle"
            statusLabel.textColor = .systemGreen
        case .streaming:
            let ip = ipField.text ?? "?"
            let port = portField.text ?? "?"
            statusLabel.text = "Status: Streaming to \(ip):\(port)"
            statusLabel.textColor = .systemGreen
        case .error(let msg):
            statusLabel.text = "Status: \(msg)"
            statusLabel.textColor = .systemRed
        }
    }
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd ios && xcodebuild -project LidarStreamer.xcodeproj -scheme LidarStreamer -destination 'generic/platform=iOS' build 2>&1 | tail -5
```

Expected: `BUILD SUCCEEDED`

- [ ] **Step 3: Commit**

```bash
git add ios/LidarStreamer/ViewController.swift
git commit -m "feat(ios): add programmatic UI layout to ViewController"
```

---

## Task 4: ViewController — ARKit + CoreMotion + Streaming

**Files:**
- Modify: `ios/LidarStreamer/ViewController.swift`

This is the core task — wires up ARSession, CMMotionManager, frame processing, downsampling, and the send loop.

- [ ] **Step 1: Add ARKit session and CoreMotion properties**

Add these properties to `ViewController`, after the existing state properties:

```swift
    private let arSession = ARSession()
    private let motionManager = CMMotionManager()
    private var frameCount = 0
    private let frameSkip = 6

    private var bootTimeOffset: TimeInterval = 0
    private var sendTimestamps: [CFTimeInterval] = []
```

- [ ] **Step 2: Add LiDAR capability check**

Add this method to `ViewController`:

```swift
    private func checkLiDAR() -> Bool {
        ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth)
    }
```

- [ ] **Step 3: Implement toggleTapped with full start/stop logic**

Replace the empty `toggleTapped` method:

```swift
    @objc private func toggleTapped() {
        if isStreaming {
            stopStreaming()
        } else {
            startStreaming()
        }
    }

    private func startStreaming() {
        guard checkLiDAR() else {
            let alert = UIAlertController(
                title: "No LiDAR",
                message: "This device does not have a LiDAR sensor.",
                preferredStyle: .alert
            )
            alert.addAction(UIAlertAction(title: "OK", style: .default))
            present(alert, animated: true)
            return
        }

        guard let ip = ipField.text, !ip.isEmpty,
              let portStr = portField.text, let port = UInt16(portStr) else {
            statusLabel.text = "Status: Invalid IP or port"
            statusLabel.textColor = .systemRed
            return
        }

        view.endEditing(true)

        // Compute boot-time to epoch offset
        bootTimeOffset = Date().timeIntervalSince1970 - ProcessInfo.processInfo.systemUptime

        // Start motion
        motionManager.deviceMotionUpdateInterval = 0.02  // 50 Hz
        motionManager.startDeviceMotionUpdates()

        // Start AR
        let config = ARWorldTrackingConfiguration()
        config.frameSemantics = .sceneDepth
        arSession.delegate = self
        arSession.run(config)

        // Start UDP
        streamer.start(host: ip, port: port)

        frameCount = 0
        sendTimestamps.removeAll()
        isStreaming = true
        toggleButton.setTitle("Stop", for: .normal)
        UIApplication.shared.isIdleTimerDisabled = true
    }

    private func stopStreaming() {
        arSession.pause()
        motionManager.stopDeviceMotionUpdates()
        streamer.stop()

        isStreaming = false
        toggleButton.setTitle("Start", for: .normal)
        UIApplication.shared.isIdleTimerDisabled = false
        fpsLabel.text = "TX: — fps"
        yawLabel.text = "Yaw: — rad (—°)"
    }
```

- [ ] **Step 4: Add app lifecycle handling**

Add these overrides to `ViewController`:

```swift
    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        if isStreaming { stopStreaming() }
    }
```

- [ ] **Step 5: Add depth downsampling helper**

Add this method to `ViewController`:

```swift
    private func downsample(depthMap: CVPixelBuffer) -> [Float32]? {
        let srcW = CVPixelBufferGetWidth(depthMap)   // 256
        let srcH = CVPixelBufferGetHeight(depthMap)   // 192
        let dstW = 64
        let dstH = 48
        let strideX = srcW / dstW  // 4
        let strideY = srcH / dstH  // 4

        CVPixelBufferLockBaseAddress(depthMap, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(depthMap, .readOnly) }

        guard let base = CVPixelBufferGetBaseAddress(depthMap) else { return nil }
        let rowBytes = CVPixelBufferGetBytesPerRow(depthMap)
        let srcPtr = base.assumingMemoryBound(to: UInt8.self)

        var result = [Float32](repeating: 0, count: dstW * dstH)
        for row in 0..<dstH {
            let srcRow = row * strideY
            let rowStart = srcPtr.advanced(by: srcRow * rowBytes)
            let floatRow = UnsafeRawPointer(rowStart).assumingMemoryBound(to: Float32.self)
            for col in 0..<dstW {
                result[row * dstW + col] = floatRow[col * strideX]
            }
        }
        return result
    }
```

- [ ] **Step 6: Add FPS tracking helper**

Add this method to `ViewController`:

```swift
    private func recordSendAndUpdateFPS() {
        let now = CACurrentMediaTime()
        sendTimestamps.append(now)
        if sendTimestamps.count > 10 {
            sendTimestamps.removeFirst()
        }
        guard sendTimestamps.count >= 2,
              let first = sendTimestamps.first, let last = sendTimestamps.last else { return }
        let elapsed = last - first
        guard elapsed > 0 else { return }
        let fps = Double(sendTimestamps.count - 1) / elapsed
        DispatchQueue.main.async {
            self.fpsLabel.text = String(format: "TX: %.1f fps", fps)
        }
    }
```

- [ ] **Step 7: Add ARSessionDelegate extension**

Add this extension at the bottom of `ViewController.swift`:

```swift
extension ViewController: ARSessionDelegate {

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        frameCount += 1
        guard frameCount % frameSkip == 0 else { return }

        guard let sceneDepth = frame.sceneDepth else { return }
        guard let yaw = motionManager.deviceMotion?.attitude.yaw else { return }
        guard let depth = downsample(depthMap: sceneDepth.depthMap) else { return }

        let timestamp = frame.timestamp + bootTimeOffset

        depth.withUnsafeBufferPointer { buf in
            guard let ptr = buf.baseAddress else { return }
            streamer.send(depth: ptr, yaw: yaw, timestamp: timestamp)
        }

        recordSendAndUpdateFPS()

        let yawDeg = yaw * 180.0 / .pi
        DispatchQueue.main.async {
            self.yawLabel.text = String(format: "Yaw: %.2f rad (%.1f°)", yaw, yawDeg)
        }
    }

    func session(_ session: ARSession, didFailWithError error: Error) {
        stopStreaming()
        statusLabel.text = "Status: AR Error: \(error.localizedDescription)"
        statusLabel.textColor = .systemRed
    }
}
```

- [ ] **Step 8: Verify it compiles**

```bash
cd ios && xcodebuild -project LidarStreamer.xcodeproj -scheme LidarStreamer -destination 'generic/platform=iOS' build 2>&1 | tail -5
```

Expected: `BUILD SUCCEEDED`

- [ ] **Step 9: Commit**

```bash
git add ios/LidarStreamer/ViewController.swift
git commit -m "feat(ios): wire ARKit + CoreMotion + UDP streaming in ViewController"
```

---

## Task 5: AppDelegate — Idle Timer + Final Wiring

**Files:**
- Modify: `ios/LidarStreamer/AppDelegate.swift`

- [ ] **Step 1: Add background/foreground notification handling**

Update `ios/LidarStreamer/AppDelegate.swift` — the idle timer is already managed by ViewController in `startStreaming()`/`stopStreaming()`. The AppDelegate just needs the window setup (already done in Task 0). No further changes needed unless the current version is missing something.

Verify `AppDelegate.swift` matches what was created in Task 0. No edits needed.

- [ ] **Step 2: Final build verification**

```bash
cd ios && xcodebuild -project LidarStreamer.xcodeproj -scheme LidarStreamer -destination 'generic/platform=iOS' build 2>&1 | tail -5
```

Expected: `BUILD SUCCEEDED`

- [ ] **Step 3: Commit**

```bash
git add ios/
git commit -m "feat(ios): LidarStreamer complete — ARKit LiDAR + UDP streaming"
```

---

## Task 6: End-to-End Verification

- [ ] **Step 1: Start the Python receiver on laptop**

```bash
cd laptop && python3 -c "from receiver import UDPReceiver; rx = UDPReceiver(); f = rx.recv(); print(f'Got frame: {f.width}x{f.height}, yaw={f.yaw:.2f}, ts={f.timestamp:.2f}')"
```

- [ ] **Step 2: Deploy iOS app to a LiDAR-equipped iPhone**

Open `ios/LidarStreamer.xcodeproj` in Xcode, select your device, build and run (Cmd+R).

- [ ] **Step 3: Verify streaming**

1. Enter the laptop's IP in the text field
2. Tap Start
3. Confirm on the Python side that `Got frame: 64x48, yaw=X.XX, ts=XXXXXXXXXX.XX` prints
4. Confirm the iOS UI shows non-zero FPS and updating yaw values

- [ ] **Step 4: Run the full hologram pipeline**

```bash
cd laptop && python3 main.py
```

Verify the hologram window appears and renders point cloud data from the iPhone's LiDAR stream.
