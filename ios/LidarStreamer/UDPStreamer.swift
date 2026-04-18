import Foundation
import Network

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
            Darwin.close(fd)
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

    // MARK: - Send

    func send(depth: UnsafePointer<Float32>, yaw: Double, timestamp: Double) {
        guard fd >= 0 else { return }

        let pixelCount = Int(outputWidth) * Int(outputHeight)
        let headerSize = 2 + 2 + 8 + 8
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
