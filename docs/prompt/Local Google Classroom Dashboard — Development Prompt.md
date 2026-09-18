You are an experienced full-stack developer and UI/UX designer. Build a complete, polished, modern local web application that connects to a user's Google Classroom account and provides a much more convenient dashboard for managing schoolwork.

The application is intended for personal use on a Windows PC and must run entirely locally. It must not require paid hosting, a cloud database, or a publicly accessible server.

PROJECT GOAL

Create a personal "Google Classroom Dashboard" that connects to Google Classroom through the official Google Classroom API and presents all important school information in one clean interface.

The application should make it easy to answer:

- What do I need to do today?
- What is overdue?
- What do I need to do tomorrow?
- What assignments are coming soon?
- Which subjects do I have?
- What grades have I received?
- What is my average grade for each subject?
- Which assignments have already been completed?
- What assignments are missing?
- When are my deadlines?

TECHNOLOGY STACK

Use:

Frontend:
- React
- TypeScript
- Vite
- Modern CSS or Tailwind CSS
- Lucide React or another clean icon library
- Responsive design

Backend:
- Python
- FastAPI
- Google APIs Python Client
- OAuth 2.0 for Google authentication

Database:
- SQLite
- SQLAlchemy if useful

The entire application must run locally.

Suggested structure:

project/
├── backend/
│   ├── main.py
│   ├── classroom_api.py
│   ├── auth.py
│   ├── database.py
│   ├── models.py
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   ├── package.json
│   └── ...
│
├── data/
│   └── classroom.db
│
├── credentials/
│   └── google OAuth credentials
│
└── README.md

GOOGLE CLASSROOM INTEGRATION

Use the official Google Classroom API.

The application must support Google OAuth 2.0.

The user should be able to click:

"Sign in with Google"

and authorize access to their Google Classroom data.

Use the minimum necessary OAuth scopes.

Do not ask for unnecessary access to the user's Google account.

After authentication, retrieve:

- Courses/classes
- Course names
- Course descriptions where available
- Teachers where available
- Coursework/assignments
- Assignment descriptions
- Due dates
- Due times
- Assignment states
- Student submissions
- Submission states
- Grades
- Maximum points
- Course materials where useful
- Links to the original Google Classroom assignment

Do not attempt to bypass Google permissions or scrape Google Classroom.

DATA SYNCHRONIZATION

The application should synchronize Google Classroom data when the dashboard is opened.

Provide a visible:

"Sync"

button.

Show:

"Last synchronized: ..."

The application should avoid unnecessary API requests by caching appropriate information locally in SQLite.

The user should always be able to manually refresh the data.

If Google Classroom is temporarily unavailable, show a friendly error and allow the user to continue viewing the last cached data.

MAIN DASHBOARD

Create a beautiful dashboard as the main screen.

The dashboard should contain:

1. OVERDUE ASSIGNMENTS

Show all assignments that:

- have passed their deadline
- have not been submitted/completed

Use a visually noticeable warning state.

Each assignment should show:

- Subject
- Assignment title
- Due date
- Status
- Points if available
- Button to open it in Google Classroom

2. TODAY

Show assignments due today.

Sort them by due time.

3. TOMORROW

Show assignments due tomorrow.

4. UPCOMING

Show assignments for the next several days.

Allow the user to configure the upcoming period, for example:

- 3 days
- 7 days
- 14 days

5. RECENTLY COMPLETED

Show recently completed assignments and their grades.

6. STATISTICS

Show useful statistics such as:

- Total assignments
- Completed assignments
- Missing assignments
- Overdue assignments
- Assignments due today
- Overall average where meaningful

SUBJECTS

Create a dedicated "Subjects" page.

Display every Google Classroom course as a subject card.

Each card should contain:

- Subject/course name
- Teacher if available
- Number of active assignments
- Number of overdue assignments
- Average grade if meaningful

Clicking a subject should open a detailed subject page.

SUBJECT DETAIL PAGE

For each subject show:

- Subject name
- Teacher
- Course description
- Average grade
- All assignments
- Completed assignments
- Incomplete assignments
- Overdue assignments
- Upcoming assignments

Allow sorting by:

- Deadline
- Status
- Grade
- Newest
- Oldest

Allow filtering:

- All
- To do
- Completed
- Overdue
- Graded
- Ungraded

GRADES

Create a dedicated "Grades" page.

Show grades grouped by subject.

Example:

Mathematics
Average: 10.4

Assignment A — 10/12
Assignment B — 11/12
Assignment C — 9/10

Physics
Average: 9.8

Include:

- Grade
- Maximum points
- Percentage when appropriate
- Assignment
- Subject
- Date

Also show a visual grade history where enough data exists.

Do not fabricate grades when Google Classroom does not provide enough information.

CALENDAR

Create a dedicated calendar page.

Display assignments by due date.

Support:

- Month view
- Week view
- Day view

Assignments should be visually distinguishable by subject.

Clicking an assignment should open its details.

ASSIGNMENT DETAILS

When an assignment is opened, show:

- Title
- Subject
- Description
- Due date
- Due time
- Status
- Grade
- Maximum points
- Submission state
- Attachments/materials where available
- Original Google Classroom link

Provide:

"Open in Google Classroom"

button.

SEARCH

Add global search.

The user should be able to search:

- Assignment names
- Subjects
- Teachers
- Assignment descriptions where available

The search should update quickly without requiring a page reload.

FILTERING AND SORTING

Provide intuitive filtering throughout the application.

Useful filters include:

- Subject
- Status
- Due date
- Grade
- Completed/incomplete

Useful sorting:

- Deadline
- Priority
- Grade
- Recently added

PRIORITY SYSTEM

Automatically calculate a simple assignment priority.

For example:

HIGH:
- overdue
- due today
- due very soon

MEDIUM:
- due tomorrow
- due within several days

LOW:
- due later

Do not modify Google Classroom data based on this priority. It is only an application-side visual organization system.

NOTIFICATIONS / REMINDERS

Because the application is local, implement optional local reminders if practical.

Allow the user to configure:

- Remind about assignments due today
- Remind about assignments due tomorrow
- Remind about overdue assignments

Do not require a cloud notification service.

If desktop notifications are difficult with the chosen architecture, implement a notification center inside the application first.

DASHBOARD CUSTOMIZATION

Allow the user to customize the dashboard.

Possible settings:

- Show/hide dashboard sections
- Choose upcoming period
- Choose default sorting
- Choose light/dark/system theme
- Compact or comfortable assignment cards

Store these preferences locally.

UI/UX DESIGN

The application should look like a modern professional productivity application, NOT like a basic school project.

Design inspiration can come from modern productivity dashboards such as Notion, Linear, Todoist, or modern Google applications, but do not copy their interfaces.

Use:

- Clean spacing
- Rounded cards
- Subtle shadows
- Clear typography
- Consistent iconography
- Strong visual hierarchy
- Smooth hover states
- Subtle transitions
- Clear status indicators
- Responsive layouts

Use a restrained color palette.

Recommended status colors:

- Red/orange for overdue
- Yellow/orange for upcoming
- Green for completed
- Neutral colors for ordinary information

Do not make the interface excessively colorful.

DARK MODE

Support:

- Light mode
- Dark mode
- System mode

The default should follow the operating system preference.

NAVIGATION

Use a sidebar on desktop.

Suggested navigation:

Dashboard
Subjects
Assignments
Grades
Calendar
Settings

The sidebar should show small counters where useful, for example:

Assignments
  5

Overdue
  2

The navigation must remain simple and uncluttered.

ASSIGNMENTS PAGE

Create a complete assignments page containing all assignments.

Use tabs or filters:

All
To Do
Overdue
Completed
Graded

Each assignment row/card should show:

Subject
Title
Deadline
Status
Grade
Priority

Allow clicking to open the assignment details.

LOADING STATES

Never show a blank screen while data is loading.

Use:

- Skeleton loaders
- Loading indicators
- Empty states

Example empty state:

"No assignments due today 🎉"

ERROR HANDLING

Create user-friendly errors.

Do not expose raw Python stack traces to the user.

Examples:

"Google authentication failed. Please try signing in again."

"Google Classroom could not be reached. Showing your last synchronized data."

"No assignments found."

OFFLINE/CACHED DATA

Since the application is local, cache useful Classroom data in SQLite.

If the user temporarily loses internet access:

- Show cached data
- Clearly indicate that the data may not be current
- Allow synchronization again when the connection returns

SECURITY

Do not hard-code:

- Google client secrets
- OAuth tokens
- API keys

Keep credentials outside the source code.

Use environment variables or local configuration files.

Never commit secrets to Git.

Store OAuth tokens securely enough for a local personal application.

SETTINGS

Create a settings page containing:

Google account connection status
Last synchronization time
Sync now
Theme
Dashboard preferences
Assignment display preferences
Notification preferences
Clear local cached data
Sign out

Provide confirmation before destructive actions such as clearing all local data.

LOCAL DEVELOPMENT

The project must be easy to start on Windows.

Provide a README.md explaining:

1. Required software
2. Python version
3. Node.js version
4. How to create a Google Cloud project
5. How to enable Google Classroom API
6. How to configure OAuth credentials
7. Where to put the credentials
8. How to install dependencies
9. How to start the backend
10. How to start the frontend
11. How to open the application
12. Common errors and their solutions

Prefer simple commands such as:

Backend:

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload

Frontend:

npm install
npm run dev

The exact commands may be adjusted to the final project structure.

API DESIGN

Create a clean backend API.

Example endpoints:

GET /api/auth/status
GET /api/courses
GET /api/assignments
GET /api/assignments/upcoming
GET /api/assignments/overdue
GET /api/grades
GET /api/calendar
POST /api/sync

Use proper HTTP status codes and structured JSON responses.

ARCHITECTURE

Keep the Google Classroom API integration separate from the rest of the application.

For example:

Google Classroom API
        ↓
classroom_api.py
        ↓
service/business logic
        ↓
SQLite
        ↓
FastAPI
        ↓
React frontend

Do not put all application logic into one Python file.

CODE QUALITY

Write clean, maintainable code.

Use:

- TypeScript types/interfaces
- Python type hints
- Pydantic models
- Clear separation of responsibilities
- Reusable React components
- Environment configuration
- Error handling
- Comments only where they provide useful context

Do not create unnecessary abstractions.

Do not use fake/mock Classroom data in the final application unless explicitly placed behind a development/test mode.

IMPORTANT CONSTRAINTS

The application is personal and local.

Do NOT require:

- paid hosting
- a VPS
- a cloud database
- a public domain
- Docker unless genuinely useful
- a paid API
- a subscription service

The only external service required for actual school data should be Google's official authentication and Google Classroom API.

The application should continue working locally even when the frontend/backend are running only on localhost.

FINAL RESULT

The final result should feel like a polished personal school productivity application rather than a raw API demo.

A user should be able to:

1. Start the backend.
2. Start the frontend.
3. Sign in with Google.
4. Grant Classroom permissions.
5. See their subjects.
6. See today's assignments.
7. See upcoming assignments.
8. See overdue assignments.
9. See completed assignments.
10. See grades.
11. Browse everything by subject.
12. Open assignments directly in Google Classroom.
13. Use a calendar.
14. Search and filter assignments.
15. Customize the dashboard.
16. Use dark/light mode.
17. Synchronize data whenever necessary.

Build the application incrementally and prioritize a working Google Classroom integration first, followed by the dashboard and UI.

Do not pretend that an API feature exists if it is not supported by the official Google Classroom API. When a requested feature is unavailable, clearly explain the limitation and implement the closest legitimate alternative.