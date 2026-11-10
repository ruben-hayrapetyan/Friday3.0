import AppKit
import CoreText

/// The icon: a white F inside a ring that closes as the week comes round to
/// Friday.
///
/// Drawn the way Apple draws its own: one mark on a deep, softly lit square,
/// nothing else. The ring is what says this icon is not a still picture — an
/// open ring reads at any size as "on its way", the same promise Activity's
/// rings make. It starts at twelve o'clock as Saturday begins, sweeps
/// clockwise through the week, and on Friday closes, in the gold a starred
/// task wears. The F is SF Rounded, so its ends match the ring's caps.
///
/// The Dock shows it live; the copy in the app bundle is drawn once, at about
/// Thursday — open, so even the still version says it moves.
enum FridayIcon {
    /// Fresh iron-gall navy (Theme.fresh), lit from above.
    private static let top = hex(0x305689)
    private static let middle = hex(0x1D365D)
    private static let bottom = hex(0x12223D)
    /// Theme.mark, brightened to hold against navy.
    private static let gold = hex(0xF2C14E)

    /// What the bundle's icon shows: most of the way there.
    static let restingProgress = 0.78

    static func image(size: CGFloat, progress: Double, isFriday: Bool = false, ribbon: String? = nil) -> NSImage {
        NSImage(size: NSSize(width: size, height: size), flipped: false) { rect in
            draw(in: rect, progress: progress, isFriday: isFriday, ribbon: ribbon)
            return true
        }
    }

    /// Draws into the current graphics context; `ribbon`, a band across the foot with its word (Friday Test's
    /// "TEST", so the two Fridays can be told apart in the Dock).
    static func draw(in canvas: NSRect, progress: Double, isFriday: Bool, ribbon: String? = nil) {
        let size = canvas.width
        // Under 64 pixels — the menu bar, a list, Finder at its smallest —
        // the drawing simplifies the way Apple's own icons do: less margin,
        // no shadow, a heavier ring and a bigger letter, so it stays an F in
        // a ring rather than a smudge.
        let small = size < 64

        // The rounded square, on the standard macOS icon grid, with the
        // shadow the system's own icons sit on.
        let inset = size * (small ? 0.04 : 0.098)
        let rect = canvas.insetBy(dx: inset, dy: inset)
        let corner = rect.width * 0.225
        let tile = NSBezierPath(roundedRect: rect, xRadius: corner, yRadius: corner)

        NSGraphicsContext.saveGraphicsState()
        if !small {
            let shadow = NSShadow()
            shadow.shadowColor = NSColor.black.withAlphaComponent(0.28)
            shadow.shadowBlurRadius = size * 0.022
            shadow.shadowOffset = NSSize(width: 0, height: -size * 0.010)
            shadow.set()
        }
        middle.setFill()
        tile.fill()
        NSGraphicsContext.restoreGraphicsState()

        NSGradient(colors: [top, middle, bottom], atLocations: [0, 0.55, 1], colorSpace: .sRGB)?
            .draw(in: tile, angle: -90)
        // A sheen on the upper half, the light the gradient implies.
        NSGraphicsContext.saveGraphicsState()
        tile.addClip()
        NSGradient(starting: NSColor.white.withAlphaComponent(0.10),
                   ending: NSColor.white.withAlphaComponent(0))?
            .draw(in: NSRect(x: rect.minX, y: rect.midY, width: rect.width, height: rect.height / 2),
                  angle: -90)
        NSGraphicsContext.restoreGraphicsState()

        let center = NSPoint(x: rect.midX, y: rect.midY)
        let radius = rect.width * (small ? 0.33 : 0.355)
        let lineWidth = max(rect.width * (small ? 0.12 : 0.082), 1.6)

        // The whole week, faintly: the ring still to go.
        let track = NSBezierPath()
        track.appendArc(withCenter: center, radius: radius, startAngle: 0, endAngle: 360)
        track.lineWidth = lineWidth
        NSColor.white.withAlphaComponent(small ? 0.22 : 0.14).setStroke()
        track.stroke()

        // How far it has come, clockwise from twelve. Never quite nothing,
        // so a Saturday icon still shows where the ring begins.
        let level = isFriday ? 1 : min(max(progress, 0.02), 0.995)
        let arc = NSBezierPath()
        arc.appendArc(withCenter: center, radius: radius,
                      startAngle: 90, endAngle: 90 - 360 * level, clockwise: true)
        arc.lineWidth = lineWidth
        arc.lineCapStyle = .round
        NSGraphicsContext.saveGraphicsState()
        let lift = NSShadow()
        if isFriday {
            // Closed: a soft gold glow rather than a shadow.
            lift.shadowColor = gold.withAlphaComponent(0.55)
            lift.shadowBlurRadius = lineWidth * 0.9
        } else {
            // The leading end sits over the track, as Activity's rings do.
            lift.shadowColor = NSColor.black.withAlphaComponent(0.35)
            lift.shadowBlurRadius = lineWidth * 0.35
        }
        if !small { lift.set() }
        (isFriday ? gold : NSColor.white).setStroke()
        arc.stroke()
        NSGraphicsContext.restoreGraphicsState()

        // The F.
        if let letter = letterF(height: rect.height * (small ? 0.36 : 0.33)) {
            let bounds = letter.bounds
            letter.transform(using: AffineTransform(translationByX: center.x - bounds.midX,
                                                    byY: center.y - bounds.midY))
            NSColor.white.setFill()
            letter.fill()
        }
        if let ribbon { band(ribbon, on: tile, in: rect, small: small) }
    }

    /// Orange, away from the gold of a closed ring and the red of something late.
    private static let orange = hex(0xE0742F)

    private static func band(_ word: String, on tile: NSBezierPath, in rect: NSRect, small: Bool) {
        let height = rect.height * (small ? 0.30 : 0.20)
        NSGraphicsContext.saveGraphicsState()
        tile.addClip()
        orange.setFill()
        NSRect(x: rect.minX, y: rect.minY, width: rect.width, height: height).fill()
        NSGraphicsContext.restoreGraphicsState()
        guard rect.width >= 28 else { return }  // smaller, the band alone says it
        let base = NSFont.systemFont(ofSize: height * 0.58, weight: .heavy)
        let font = base.fontDescriptor.withDesign(.rounded).flatMap { NSFont(descriptor: $0, size: base.pointSize) } ?? base
        let text = NSAttributedString(string: word, attributes: [
            .font: font, .foregroundColor: NSColor.white, .kern: height * 0.06,
        ])
        let size = text.size()
        text.draw(at: NSPoint(x: rect.midX - size.width / 2, y: rect.minY + (height - size.height) / 2 + height * 0.03))
    }

    /// The outline of "F" in SF Rounded, heavy, at a cap height of `height`.
    private static func letterF(height: CGFloat) -> NSBezierPath? {
        let base = NSFont.systemFont(ofSize: 100, weight: .heavy)
        let descriptor = base.fontDescriptor.withDesign(.rounded) ?? base.fontDescriptor
        guard let rounded = NSFont(descriptor: descriptor, size: 100) else { return nil }
        let font = rounded as CTFont
        var character: UniChar = 0x46   // F
        var glyph: CGGlyph = 0
        guard CTFontGetGlyphsForCharacters(font, &character, &glyph, 1),
              let path = CTFontCreatePathForGlyph(font, glyph, nil) else { return nil }
        let outline = NSBezierPath(cgPath: path)
        let scale = height / max(outline.bounds.height, 1)
        outline.transform(using: AffineTransform(scaleByX: scale, byY: scale))
        return outline
    }

    private static func hex(_ value: UInt32) -> NSColor {
        NSColor(srgbRed: CGFloat((value >> 16) & 0xFF) / 255,
                green: CGFloat((value >> 8) & 0xFF) / 255,
                blue: CGFloat(value & 0xFF) / 255,
                alpha: 1)
    }
}

/// Keeps the Dock icon on today: redrawn at launch, when the day changes or
/// the clock jumps, and every half hour in between so the ring creeps round.
/// Half-hourly is plenty — it moves about a third of a percent an hour.
@MainActor
final class DockIcon {
    private var observers: [NSObjectProtocol] = []
    private var timer: Timer?
    /// A word on a band across the icon's foot (FridayIcon.draw).
    var ribbon: String?

    func start() {
        update()
        for name in [Notification.Name.NSCalendarDayChanged, .NSSystemClockDidChange,
                     .NSSystemTimeZoneDidChange] {
            observers.append(NotificationCenter.default.addObserver(
                forName: name, object: nil, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.update() }
            })
        }
        timer = Timer.scheduledTimer(withTimeInterval: 30 * 60, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.update() }
        }
        timer?.tolerance = 5 * 60
    }

    func update() {
        let calendar = Calendar.autoupdatingCurrent
        let countdown = FridayCountdown(at: Date(), calendar: calendar)
        NSApp.applicationIconImage = FridayIcon.image(size: 512,
                                                      progress: countdown.progress,
                                                      isFriday: countdown.isFriday,
                                                      ribbon: ribbon)
    }
}
