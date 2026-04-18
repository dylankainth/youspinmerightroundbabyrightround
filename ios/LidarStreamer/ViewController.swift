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

    private let arSession = ARSession()
    private let motionManager = CMMotionManager()
    private var frameCount = 0
    private let frameSkip = 6

    private var bootTimeOffset: TimeInterval = 0
    private var sendTimestamps: [CFTimeInterval] = []

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

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        if isStreaming { stopStreaming() }
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

        bootTimeOffset = Date().timeIntervalSince1970 - ProcessInfo.processInfo.systemUptime

        motionManager.deviceMotionUpdateInterval = 0.02
        motionManager.startDeviceMotionUpdates()

        let config = ARWorldTrackingConfiguration()
        config.frameSemantics = .sceneDepth
        arSession.delegate = self
        arSession.run(config)

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

    // MARK: - Helpers

    private func checkLiDAR() -> Bool {
        ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth)
    }

    private func downsample(depthMap: CVPixelBuffer) -> [Float32]? {
        let srcW = CVPixelBufferGetWidth(depthMap)
        let srcH = CVPixelBufferGetHeight(depthMap)
        let dstW = 64
        let dstH = 48
        let strideX = srcW / dstW
        let strideY = srcH / dstH

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
        DispatchQueue.main.async { [weak self] in
            self?.fpsLabel.text = String(format: "TX: %.1f fps", fps)
        }
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

// MARK: - ARSessionDelegate

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
        DispatchQueue.main.async { [weak self] in
            self?.yawLabel.text = String(format: "Yaw: %.2f rad (%.1f°)", yaw, yawDeg)
        }
    }

    func session(_ session: ARSession, didFailWithError error: Error) {
        stopStreaming()
        statusLabel.text = "Status: AR Error: \(error.localizedDescription)"
        statusLabel.textColor = .systemRed
    }
}
