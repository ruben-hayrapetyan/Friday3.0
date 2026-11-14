import SwiftUI

/// The start (28 Oct: "make the loading symbol be a play on the logo... the friday bar fills up and then turns gold
/// (symbolizing friday) and then it opens up to the app"). The app's icon, drawn live: its ring fills while Friday
/// starts, closes in the gold Friday wears once the app has drawn, and the tile opens out into it.
///
/// How far the ring has come can't be measured (a first start compiles the scheduler, up to a minute; a warm one is
/// under a second), so it creeps: quickly at first, then ever more slowly, never stopping and never closing on its
/// own. Only the app being ready closes it.
enum LaunchCurve {
    // Quick through the middle, a pause on the gold (28 Oct: "pauses more on the golden ring then the middle").
    static let fill = 0.30  // seconds to close the ring from wherever it is
    static let goldAt = 0.15  // the ring turns gold as it closes
    static let gold = 0.20
    static let openAt = 0.95  // over half a second in gold, then the tile opens
    static let open = 0.35
    /// From "ready" to the app shown.
    static var total: Double { openAt + open }

    /// The ring while waiting, `t` seconds in: over two fifths at half a second, nearly two thirds at one, 0.83 at
    /// ten, 0.91 at a minute; it never reaches 0.92.
    static func creep(_ t: Double) -> Double {
        let t = max(t, 0)
        return max(0.02, 0.78 * (1 - exp(-t / 0.6)) + 0.14 * (1 - exp(-t / 25)))
    }

    struct Frame: Equatable {
        var fill: Double  // 0 to 1, the ring
        var gold: Double  // 0 white, 1 gold
        var open: Double  // 0 the icon, 1 the app
    }

    /// The icon `t` seconds after the start, the app ready `ready` seconds after it (nil: not yet).
    static func frame(at t: Double, readyAt ready: Double?) -> Frame {
        guard let ready, t >= ready else { return Frame(fill: creep(t), gold: 0, open: 0) }
        let s = t - ready
        let from = creep(ready)
        return Frame(
            fill: from + (1 - from) * easeOut(s / fill),
            gold: smooth((s - goldAt) / gold),
            open: smooth((s - openAt) / open)
        )
    }

    static func easeOut(_ x: Double) -> Double {
        let x = min(max(x, 0), 1)
        return 1 - pow(1 - x, 3)
    }

    static func smooth(_ x: Double) -> Double {
        let x = min(max(x, 0), 1)
        return x * x * (3 - 2 * x)
    }
}

/// The icon (`FridayIcon`, drawn in SwiftUI so it can move): the F inside its ring on the navy tile.
struct FridayMark: View {
    var size: CGFloat
    var fill: Double
    var gold: Double

    private static let top = Color(red: 0x30 / 255, green: 0x56 / 255, blue: 0x89 / 255)
    private static let middle = Color(red: 0x1D / 255, green: 0x36 / 255, blue: 0x5D / 255)
    private static let bottom = Color(red: 0x12 / 255, green: 0x22 / 255, blue: 0x3D / 255)
    static let goldColor = Color(red: 0xF2 / 255, green: 0xC1 / 255, blue: 0x4E / 255)

    var body: some View {
        let tile = RoundedRectangle(cornerRadius: size * 0.225, style: .continuous)
        let line = size * 0.082
        let ring = size * 0.71  // the ring's diameter: 0.355 of the tile on each side, as the icon's
        ZStack {
            tile.fill(LinearGradient(stops: [.init(color: Self.top, location: 0), .init(color: Self.middle, location: 0.55),
                                             .init(color: Self.bottom, location: 1)],
                                     startPoint: .top, endPoint: .bottom))
            // The sheen on the upper half, the light the gradient implies.
            tile.fill(LinearGradient(colors: [.white.opacity(0.10), .white.opacity(0)], startPoint: .top, endPoint: .center))
            Circle()
                .stroke(.white.opacity(0.14), lineWidth: line)
                .frame(width: ring, height: ring)
            Circle()
                .trim(from: 0, to: fill)
                .stroke(Color.white.mix(Self.goldColor, by: gold), style: StrokeStyle(lineWidth: line, lineCap: .round))
                .rotationEffect(.degrees(-90))  // from twelve o'clock, clockwise, as the week goes
                .frame(width: ring, height: ring)
                .shadow(color: Self.goldColor.opacity(0.6 * gold), radius: line * 0.9 * gold)
                .shadow(color: .black.opacity(0.35 * (1 - gold)), radius: line * 0.35)
            Text("F")
                .font(.system(size: size * 0.45, weight: .heavy, design: .rounded))
                .foregroundStyle(.white)
                .offset(y: -size * 0.012)
        }
        .frame(width: size, height: size)
        .shadow(color: .black.opacity(0.28), radius: size * 0.022, y: size * 0.010)
        .accessibilityHidden(true)
    }
}

private extension Color {
    /// This color moved `amount` of the way to `other`.
    func mix(_ other: Color, by amount: Double) -> Color {
        let a = NSColor(self).usingColorSpace(.sRGB) ?? .white
        let b = NSColor(other).usingColorSpace(.sRGB) ?? .white
        let t = CGFloat(min(max(amount, 0), 1))
        return Color(red: Double(a.redComponent + (b.redComponent - a.redComponent) * t),
                     green: Double(a.greenComponent + (b.greenComponent - a.greenComponent) * t),
                     blue: Double(a.blueComponent + (b.blueComponent - a.blueComponent) * t))
    }
}

/// The window while Friday starts: the icon filling, a line saying what's happening, and, once the app has drawn,
/// the gold close and the opening. `onOpened` is told when the app shows.
struct LaunchView: View {
    var state: Server.State
    var slow: Bool
    var ready: Bool  // the app has drawn itself behind this
    var onOpened: () -> Void

    @Environment(\.colorScheme) private var scheme
    @State private var start = Date()
    @State private var readyAt: Date?
    private let still = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion

    var body: some View {
        TimelineView(.animation) { context in
            let t = context.date.timeIntervalSince(start)
            let frame = LaunchCurve.frame(at: t, readyAt: readyAt.map { $0.timeIntervalSince(start) })
            ZStack {
                // Friday's own page color, so the opening runs into the app rather than a flash.
                (scheme == .dark ? Color(red: 0x0F / 255, green: 0x11 / 255, blue: 0x13 / 255)
                                 : Color(red: 0xEC / 255, green: 0xEE / 255, blue: 0xE9 / 255))
                    .opacity(1 - frame.open)
                VStack(spacing: 22) {
                    FridayMark(size: 112, fill: frame.fill, gold: frame.gold)
                        .scaleEffect(still ? 1 : 1 + 0.55 * frame.open)
                    VStack(spacing: 6) {
                        Text(said)
                            .font(.system(size: 13, weight: .medium))
                            .foregroundStyle(.secondary)
                            .contentTransition(.opacity)
                        if slow {
                            Text("Getting Friday ready. The first start on a Mac can take a minute.")
                                .font(.callout)
                                .foregroundStyle(.tertiary)
                                .multilineTextAlignment(.center)
                                .frame(maxWidth: 340)
                        }
                    }
                    .opacity(1 - LaunchCurve.smooth(frame.gold * 2))
                }
                .opacity(1 - frame.open)
            }
        }
        .ignoresSafeArea()
        .allowsHitTesting(readyAt == nil)
        .onAppear { if ready { opening() } }
        .onChange(of: ready) { _, now in if now { opening() } }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(said)
    }

    private var said: String {
        if readyAt != nil { return "Friday" }
        switch state {
        case .looking: return "Finding Friday…"
        case .starting: return "Starting Friday…"
        default: return "Opening your week…"
        }
    }

    private func opening() {
        guard readyAt == nil else { return }
        readyAt = Date()
        DispatchQueue.main.asyncAfter(deadline: .now() + LaunchCurve.total) { onOpened() }
    }
}
