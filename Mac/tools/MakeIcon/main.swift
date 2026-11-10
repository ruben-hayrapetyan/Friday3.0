// Renders the bundle's icon into an .iconset — the ring at about Thursday — from
// the same drawing as the live Dock icon (Sources/App/FridayIcon.swift).
//
//   makeicon <out.iconset> [--ribbon WORD]   the icon, every size macOS asks for (Friday Test's: "TEST")
//   makeicon --week <out.png> [size]   Saturday to Friday side by side, for review
import AppKit

func png(size: CGFloat, draw: (NSRect) -> Void) -> NSBitmapImageRep? {
    let px = Int(size)
    guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px,
                                     bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                     isPlanar: false, colorSpaceName: .deviceRGB,
                                     bytesPerRow: 0, bitsPerPixel: 0) else { return nil }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    draw(NSRect(x: 0, y: 0, width: size, height: size))
    NSGraphicsContext.restoreGraphicsState()
    return rep
}

let arguments = Array(CommandLine.arguments.dropFirst())

if arguments.first == "--week", arguments.count >= 2 {
    // Saturday morning through Friday, one tile a day, at noon.
    let tile = CGFloat(Double(arguments.count > 2 ? arguments[2] : "256") ?? 256)
    let calendar = Calendar(identifier: .gregorian)
    let saturday = calendar.date(from: DateComponents(year: 2026, month: 10, day: 10, hour: 12))!
    let strip = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(tile) * 7, pixelsHigh: Int(tile),
                                 bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                 colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: strip)
    NSColor(srgbRed: 0.925, green: 0.933, blue: 0.914, alpha: 1).setFill()
    NSRect(x: 0, y: 0, width: tile * 7, height: tile).fill()
    for day in 0..<7 {
        let now = calendar.date(byAdding: .day, value: day, to: saturday)!
        let countdown = FridayCountdown(at: now, calendar: calendar)
        FridayIcon.draw(in: NSRect(x: tile * CGFloat(day), y: 0, width: tile, height: tile),
                        progress: countdown.progress, isFriday: countdown.isFriday)
    }
    NSGraphicsContext.restoreGraphicsState()
    try strip.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: arguments[1]))
    exit(0)
}

guard let outPath = arguments.first else {
    FileHandle.standardError.write(Data("usage: makeicon <out.iconset> [--ribbon WORD] | --week <out.png> [size]\n".utf8))
    exit(1)
}
let out = URL(fileURLWithPath: outPath)
let ribbon = arguments.count >= 3 && arguments[1] == "--ribbon" ? arguments[2] : nil
try? FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)

let variants: [(CGFloat, String)] = [
    (16, "icon_16x16.png"),    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
]
for (size, name) in variants {
    let rep = png(size: size) { rect in
        FridayIcon.draw(in: rect, progress: FridayIcon.restingProgress, isFriday: false, ribbon: ribbon)
    }
    try rep?.representation(using: .png, properties: [:])?.write(to: out.appendingPathComponent(name))
}
print("icons written to \(out.path)")
