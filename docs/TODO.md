# Roadmap

This roadmap contains the active backlog plus transferred completed capability history for Resume,
Calendar, and the Knowledge database. Checked history records what the product already supports;
unchecked entries remain active work unless a later product decision supersedes them.

## Telegram Bot

- [ ] Trusted users (Many TG users to One site user)
- [ ] Notifications
  - [ ] Birthdays and dates
  - [ ] Events
- [ ] Quick add (only with buttons)
  - [ ] Scrap links
    - [ ] Recipes category
    - [ ] Places category
    - [ ] Watch later category

## Finance tracker

- [ ] Categories
- [ ] CRUD for income and expences items
- [ ] Limits
  - [ ] Initial balance amount
  - [ ] Set limits to expences (no solid limits, only soft notifications about limits overdraft)
  - [ ] Shows limits overdraft 
- [ ] Telegram bot integration
  - [ ] Quick add
- [ ] Per-user settings
  - [ ] Workspace statistic chosen period
- [ ] Workspace
  - [ ] Statistic
    - [ ] Main page
      - [ ] 2 vertical bar charts with initial balance amount and balance at the end of the period
      - [ ] 2 separated tables - income and expences with columns: category name, estimated (limit), actual, diff (estimated minus actual)
      - [ ] 2 horizontal bar charts for income: estimated and actual
      - [ ] 2 horizontal bar charts for expences: estimated and actual
    - [ ] Income
      - [ ] Dynamic by previous periods
      - [ ] Pie chart by categories
    - [ ] Expences
      - [ ] Dynamic by previous periods
      - [ ] Pie chart by categiries
    - [ ] Periods - no limits incuded. Limits applies and shows only on current month.
      - [ ] this month (only current month)
      - [ ] this year (only current year)
      - [ ] this week (only current week)
      - [ ] this day (only today)
      - [ ] last week (7 days to current date)
      - [ ] last month (30 days to current date)
      - [ ] last year (365 days to cuurent date)
      - [ ] save filter preset in settings

## Per-user settings

- [ ] One page with all settings
- [ ] Themes
  - [ ] Light/Dark
  - [ ] General Color schema (affect markdown editor and preview too)
- [ ] Layout
  - [ ] Workspace items opened or closed
- [ ] Telegram bot integration
  - [ ] Initial setup
    - [ ] Telegram bot ON/OFF
    - [ ] Generate token for bot trusted users (Invites to bot)
    - [ ] Telegram bot token set
  - [ ] Notifications
    - [ ] Birthdays: ON/FF
    - [ ] Dates: ON/OFF
    - [ ] Events: ON/OFF
  - [ ] multi-choice of available "Quick add" categories

## Resume

- [x] Resume
  - [x] Store private structured ATS-oriented resume documents outside the knowledge database.
  - [x] Store each resume as a single-language document with required saved RU/EN language.
  - [x] Add protected backend CRUD API under `/api/resumes`.
  - [x] Scope resume CRUD to the authenticated author so users only list and mutate their own resumes.
  - [x] Add workspace navigation and routes at `/resumes` and `/resumes/:id`.
  - [x] Add list, create with language selection, detail edit, language badge, selected-language preview, and delete UI.
  - [x] Keep resumes private: no public pages, sitemap entries, SEO, or themes in v1.
  - [ ] Improve validation: min/max for all parts 
  - [x] Fix resume multilines fields: text with \\n to array.
  - [ ] AI
    - [ ] Advices of resume improvement
    - [ ] Analyze vacancy requirements and match against resume
    - [ ] Generate cover letter
  - [ ] New blocks and fields
    - [ ] Projects
      - [ ] Team size
      - [ ] Scale
    - [ ] Photo
  - [ ] Resume customization
    - [ ] Blocks order (Title, Photo, Summary, Experience, etc.)
    - [ ] Blocks visibility
    - [ ] Themes
  - [ ] Preview
    - [ ] Show real DOCS/PDF preview
  - [x] Resume export
    - [x] To PDF
    - [x] To DOCX
    - [x] Step-by-step maximize resume export ATS score.
    - [x] Fix readability of exported resume
    - [ ] Apply customization to exported resume

## Calendar

- [x] Base calendar view in dashboard.
- [ ] Add day, week, and year views alongside the dashboard calendar month view.
- [ ] Clickable calendar day
  - [ ] Click on empty area -> Open 1 day detail modal
  - [ ] Click on event -> Open event detail modal
- [ ] Add events from calendar
  - [ ] Person birthdays
  - [ ] Memorable Dates
  - [ ] One-time or recurring Events

## TODOs

- [ ] CRUD for TODOs
- [ ] separated TODO lists
- [ ] Telegram bot integration
  - [ ] Quick add

## Knowledge database

Each knowledge item has its own subfolder in the Knowledge section of the workspace sidebar.

- [ ] Workspace
  - [ ] Main page
    - [ ] Important info (in-dashboard CRUD – only text oneline items)
    - [x] Dates and birthdays (current and next month)
    - [ ] Recently changed files
- [ ] Knowledge item
  - [ ] Books
    - [ ] All books page
    - [ ] All read books page
    - [ ] Books to buy page
    - [ ] Books by categories page
    - [ ] Books to reread page
  - [ ] Companies
  - [x] Dates
    - [ ] Related dates
      - [ ] Nth day of the year. Example: Programmer's Day — 256th day of the year
      - [ ] Nth weekday of the month: First / Second / Third / Fourth / Fifth / Last. Example: Thanksgiving — fourth Thursday of November
      - [ ] Weekday relative to a fixed date
        - [ ] First weekday before date
        - [ ] First weekday after date
        - [ ] Nearest weekday to date
        - [ ] Example: Monday before May 25
      - [ ] Relative to another date
        - [ ] N days/weeks/months before another date
        - [ ] N days/weeks/months after another date
        - [ ] First/Last/Nth weekday before/after another date
        - [ ] Example: Good Friday — 2 days before Easter
        - [ ] Example: Maslenitsa — relative to Easter
      - [ ] Easter
        - [ ] Western / Gregorian Easter
        - [ ] Orthodox / Julian Easter
      - [ ] Date in another calendar
        - [ ] Select calendar
          - [ ] Gregorian
          - [ ] Julian
          - [ ] Hebrew
          - [ ] Islamic
          - [ ] Chinese
          - [ ] Other calendars
        - [ ] Select calendar type in date creation form
        - [ ] Convert result to chosen calendar
      - [ ] Lunar / lunisolar calendar date
        - [ ] Select calendar/calculation system
          - [ ] Islamic calendar
          - [ ] Hebrew calendar
          - [ ] Chinese calendar
          - [ ] Other lunar/lunisolar calendars
        - [ ] Month + day according to selected calendar
        - [ ] Example: Eid al-Fitr — 1 Shawwal
        - [ ] Example: Chinese New Year — first day of first Chinese lunar month
      - [ ] Astronomical event
        - [ ] Equinox
        - [ ] Solstice
        - [ ] New moon
        - [ ] Full moon
        - [ ] Other astronomical event
        - [ ] Optional timezone/location for determining local date
      - [ ] Astronomical condition relative to date
        - [ ] First full moon after date
        - [ ] First new moon after date
        - [ ] First/Last/Nth weekday after astronomical event
      - [ ] Last/First day of month
        - [ ] First day of month
        - [ ] Last day of month
        - [ ] Example: last day of February automatically handles leap years
      - [ ] Conditional by year
        - [ ] Every N years
        - [ ] Starting from specific year
        - [ ] Only before/after specific year
        - [ ] Only within year range
      - [ ] Leap year condition
        - [ ] Only in leap years
        - [ ] Only in non-leap years
      - [ ] Multi-day event
        - [ ] Duration in days
        - [ ] Start date calculated by any supported rule
        - [ ] Example: holiday/festival lasting 7 days
      - [ ] Observed / substitute date
        - [ ] If Saturday → previous Friday / next Monday
        - [ ] If Sunday → next Monday
        - [ ] If weekend → next working day
        - [ ] Custom weekday replacement rules
        - [ ] Keep original date + create observed date or replace original date
      - [ ] Date overrides / exceptions
        - [ ] Override calculated date for specific year
        - [ ] Disable event for specific year
        - [ ] Add additional date for specific year
        - [ ] Example: normally calculated date, but manually set different date in 2028
  - [x] People
    - [ ] Show/Hide (and Notify/Not) persons birthdays in calendar
  - [ ] Places
  - [ ] Projects
  - [ ] Recipes
  - [ ] Software
  - [ ] Techchecks
  - [ ] Techniques
  - [ ] Technologies
- [ ] Export Obsidian vault to knowledge database
- [ ] Add reminders for knowledge dates and birthdays.
- [ ] Add extended knowledge database search across item types and fields.
- [ ] Automate and test backup/restore for the private knowledge object bucket.

## Refactoring

- [x] Remove obsolete product prefixes; the workspace has no separate management panel.
- [x] Serve the protected workspace dashboard directly at `/` and protected product APIs at
  `/api/<domain>`.
- [x] Remove the inherited how-this-site-is-built, updates, sitemap, robots, SEO, and SSR artifacts.

## Errors

...
