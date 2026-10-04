// 生成 1024×1024 的 App 图标 PNG：深色圆角底 + 白色公文包 + 绿色对勾徽标。
// 用法：swift make-icon.swift <输出.png>

import AppKit

let out = CommandLine.arguments.dropFirst().first ?? "icon.png"
let size = 1024
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
                           bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                           colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)

// macOS 图标网格：内容区 824，四周留 100。
let tile = NSRect(x: 100, y: 100, width: 824, height: 824)
let shape = NSBezierPath(roundedRect: tile, xRadius: 185, yRadius: 185)
NSGradient(starting: NSColor(srgbRed: 0.17, green: 0.22, blue: 0.30, alpha: 1),
           ending: NSColor(srgbRed: 0.06, green: 0.08, blue: 0.12, alpha: 1))!.draw(in: shape, angle: -90)
NSColor(white: 1, alpha: 0.08).setStroke()
shape.lineWidth = 4
shape.stroke()

func symbol(_ name: String, pointSize: CGFloat, colors: [NSColor]) -> NSImage {
    let config = NSImage.SymbolConfiguration(pointSize: pointSize, weight: .semibold)
        .applying(.init(paletteColors: colors))
    return NSImage(systemSymbolName: name, accessibilityDescription: nil)!.withSymbolConfiguration(config)!
}

let case_ = symbol("briefcase.fill", pointSize: 400, colors: [NSColor(white: 0.96, alpha: 1)])
let caseRect = NSRect(x: 512 - case_.size.width / 2, y: 470 - case_.size.height / 2,
                      width: case_.size.width, height: case_.size.height)
case_.draw(in: caseRect)

let badge = symbol("checkmark.circle.fill", pointSize: 230,
                   colors: [.white, NSColor(srgbRed: 0.20, green: 0.80, blue: 0.47, alpha: 1)])
let badgeRect = NSRect(x: 700 - badge.size.width / 2, y: 300 - badge.size.height / 2,
                       width: badge.size.width, height: badge.size.height)
// 徽标外圈用底色描一圈，和公文包分开。
NSColor(srgbRed: 0.08, green: 0.10, blue: 0.15, alpha: 1).setFill()
NSBezierPath(ovalIn: badgeRect.insetBy(dx: -14, dy: -14)).fill()
badge.draw(in: badgeRect)

NSGraphicsContext.restoreGraphicsState()
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
