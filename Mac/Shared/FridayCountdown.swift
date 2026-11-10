import Foundation

/// How far the week has come toward Friday — what the Dock icon shows.
///
/// The count starts the moment the last Friday ends (Saturday, 00:00) and
/// fills over the six days to the next one. All of Friday itself reads as
/// full.
struct FridayCountdown: Equatable {
    /// 0 at the start of Saturday, approaching 1 as Friday nears; 1 all Friday.
    let progress: Double
    /// The Friday being counted toward — today, on a Friday.
    let friday: Date
    let isFriday: Bool

    init(at now: Date, calendar: Calendar) {
        let today = calendar.startOfDay(for: now)
        // Gregorian weekday numbers, whatever the locale's first day:
        // 1 is Sunday, 6 is Friday, 7 is Saturday.
        let weekday = calendar.component(.weekday, from: today)
        if weekday == 6 {
            progress = 1
            friday = today
            isFriday = true
            return
        }
        let daysAhead = (6 - weekday + 7) % 7
        let fridayStart = calendar.date(byAdding: .day, value: daysAhead, to: today) ?? today
        let saturday = calendar.date(byAdding: .day, value: -6, to: fridayStart) ?? today
        // Measured, not assumed to be six days: a week with a clock change
        // in it is an hour longer or shorter.
        let span = fridayStart.timeIntervalSince(saturday)
        progress = span > 0 ? min(max(now.timeIntervalSince(saturday) / span, 0), 1) : 0
        friday = fridayStart
        isFriday = false
    }
}
