# GoogleClassHelp — Production Windows Application

You are working on my existing local Google Classroom dashboard project.

Your task is to transform the current development project into a distributable Windows application that can be launched by double-clicking a single executable.

## Important

- Use **Nuitka**, NOT PyInstaller.
- Do not replace the existing architecture unnecessarily.
- Do not break the existing Google Classroom API integration.
- Do not change OAuth scopes unless absolutely necessary.
- Preserve the current functionality of the application.
- This is a local-first application.
- The user should not need PyCharm, VS Code, Python, Node.js, npm, or a development environment after installation.

## Current development workflow

Backend:

```text
cd D:\Documents\google_class_help
.venv\Scripts\activate
cd backend
uvicorn main:app --reload
```

Frontend:

```text
cd frontend
npm install
npm run dev
```

Backend:

```text
http://127.0.0.1:8000
```

Frontend development server:

```text
http://localhost:5173
```

# Goal

Convert the project into a production-style Windows application with this user experience:

1. User double-clicks:

```text
GoogleClassHelp.exe
```

2. The application starts the local backend.
3. The application serves the already-built frontend through the backend.
4. The application waits until the backend is ready.
5. The application automatically opens the user's default browser.
6. The browser opens:

```text
http://127.0.0.1:8000
```

7. The user sees the Google Classroom dashboard.
8. No terminal/CMD window should be visible in the final build.
9. The user should not need to manually start separate frontend and backend processes.

# Architecture

Change the production architecture from:

```text
Browser
   ↓
Vite dev server :5173
   ↓
FastAPI :8000
```

to:

```text
GoogleClassHelp.exe
   ↓
FastAPI
   ├── REST API
   └── frontend/dist
          ↓
       Browser
          ↓
   http://127.0.0.1:8000
```

The production frontend must be built using:

```text
npm run build
```

Do NOT use:

```text
npm run dev
```

in the final application.

# FastAPI frontend serving

Configure FastAPI to serve the production frontend from:

```text
frontend/dist
```

The application should:

- serve static assets correctly;
- serve `index.html`;
- support client-side routing if the frontend uses React Router;
- keep `/api/...` routes separate from frontend routes;
- return the frontend's `index.html` for unknown frontend routes when appropriate.

Do not break existing API endpoints.

# Application launcher

Create a dedicated production launcher, for example:

```text
backend/launcher.py
```

The launcher must:

1. Determine its own installation/application directory reliably.
2. Start the FastAPI application.
3. Use bundled application resources correctly.
4. Wait until the backend is actually ready.
5. Open the default browser automatically.
6. Keep the backend alive while the application is running.
7. Shut down cleanly when the application exits.
8. Handle startup errors gracefully.
9. Avoid hard-coded development paths such as:

```text
D:\Documents\google_class_help
```

The application must work when installed somewhere else, for example:

```text
C:\Program Files\GoogleClassHelp\
```

or:

```text
C:\Users\User\AppData\Local\GoogleClassHelp\
```

# Important development/production separation

Development mode can continue to use:

```text
uvicorn main:app --reload
```

but production mode must NOT use `--reload`.

Do not depend on the current working directory.

Use paths relative to the executable/application location or an appropriate application-data directory.

# Google OAuth credentials

The project currently contains:

```text
backend/credentials.json
```

Do NOT distribute this as a normal readable JSON file next to the final executable.

The goal is to prevent a normal user from accidentally opening `credentials.json` in Notepad or another text editor.

Do NOT simply rename the file.

Do NOT store the encryption key in another obvious plaintext file beside the executable.

Instead, design the production build so the OAuth client configuration is bundled into the application.

Prefer an approach where the credentials are:

- included as an application resource;
- optionally encrypted/obfuscated at rest inside the executable;
- loaded by the application at runtime;
- preferably kept in memory rather than creating a permanent plaintext `credentials.json` file.

## Important security limitation

Do NOT claim that embedding/encrypting Desktop OAuth credentials makes them impossible to extract.

This is a desktop application. Anything required by the application at runtime can theoretically be recovered by someone performing reverse engineering.

The purpose here is:

- prevent accidental exposure;
- avoid distributing `credentials.json` as a visible file;
- make casual inspection harder;
- follow reasonable desktop-app security practices.

Do not over-engineer this into a false "unbreakable encryption" system.

# OAuth token storage

Do NOT bundle a user's `token.json` into the executable.

Each user must have their own OAuth authorization.

Store user-specific OAuth tokens in an appropriate per-user application-data directory, for example:

```text
%LOCALAPPDATA%\GoogleClassHelp\
```

such as:

```text
%LOCALAPPDATA%\GoogleClassHelp\token.json
```

The application should create the directory automatically.

The token must never be hard-coded into the application.

The application should:

- use an existing token when available;
- refresh it when required;
- launch OAuth authorization when no valid token exists;
- preserve the token between application launches.

Do not commit `token.json` to Git.

# Google OAuth

Preserve the existing Google Classroom OAuth flow.

Do not replace the Desktop OAuth flow with a custom insecure authentication mechanism.

Do not ask users to manually copy credential files into the application directory.

Do not expose OAuth tokens through the frontend.

The frontend should communicate with the local FastAPI backend, and the backend should communicate with Google Classroom.

# File path handling

The application must work correctly both:

1. During development:

```text
google_class_help/
backend/
frontend/
```

and:

2. After Nuitka compilation:

```text
GoogleClassHelp.exe
```

Do not assume:

```python
Path.cwd()
```

is the project root.

Do not use hard-coded absolute paths.

Create a robust path abstraction that distinguishes:

- bundled application resources;
- user-writable application data;
- temporary files;
- development paths.

Conceptually:

```text
RESOURCE_DIR
DATA_DIR
```

`RESOURCE_DIR`:
read-only application resources bundled with the application.

`DATA_DIR`:
user-specific writable data such as `token.json` and local database files.

# Nuitka

Use **Nuitka as the only Python application compiler/packager**.

Do NOT use PyInstaller.

The final Windows build should be created with Nuitka.

Prefer a production configuration appropriate for a Windows desktop application.

Investigate and use the correct Nuitka options for:

- standalone compilation;
- onefile distribution if appropriate;
- including `frontend/dist`;
- including required Python packages;
- including OAuth-related resources;
- including FastAPI/Uvicorn dependencies;
- excluding unnecessary development dependencies;
- Windows GUI/no-console mode for the final build.

Do not blindly add hundreds of `--include-package` options.

First determine what Nuitka actually needs based on imports and runtime behavior.

The final target should ideally be:

```text
GoogleClassHelp.exe
```

rather than requiring a Python environment.

# Nuitka resource handling

Frontend files from:

```text
frontend/dist/
```

must be included in the final application.

The build process must reliably include:

- `index.html`;
- JavaScript bundles;
- CSS;
- images;
- fonts;
- other static assets.

Do not assume that files existing in the source directory will automatically exist inside a Nuitka binary.

Explicitly configure the required data files/directories.

# Build pipeline

Create a repeatable production build process.

For example:

```text
build.bat
```

The production build should roughly perform:

1. Clean previous frontend build if appropriate.
2. Install frontend dependencies if required.
3. Run:

```text
npm run build
```

4. Verify that `frontend/dist` exists.
5. Build the Python application using Nuitka.
6. Include the required frontend resources.
7. Produce the final Windows executable.
8. Optionally copy only required release files into a release directory.

Do not include:

- `.venv`
- `node_modules`
- source maps if unnecessary for release
- development files
- test files
- `credentials.json` as a separate plaintext file
- `token.json`
- Git files

# Final user experience

The final application should behave approximately like this:

```text
Double-click GoogleClassHelp.exe
        ↓
Application starts
        ↓
FastAPI starts locally
        ↓
Application checks:
http://127.0.0.1:8000
        ↓
Backend ready
        ↓
Default browser opens automatically
        ↓
Google Classroom Dashboard
```

# First run

On the first run, if the user has no OAuth token:

```text
GoogleClassHelp.exe
        ↓
Browser opens
        ↓
Google OAuth authorization
        ↓
User grants Classroom permissions
        ↓
OAuth token saved to:
%LOCALAPPDATA%\GoogleClassHelp\
        ↓
Dashboard becomes available
```

On subsequent launches:

```text
GoogleClassHelp.exe
        ↓
existing token loaded
        ↓
backend starts
        ↓
browser opens
        ↓
Dashboard
```

# Local database

If the project already uses SQLite or another local database, preserve it.

Store writable database files in an appropriate user-data directory rather than inside a read-only installation directory such as:

```text
C:\Program Files\...
```

For example:

```text
%LOCALAPPDATA%\GoogleClassHelp\data\
```

# Logging and error handling

Because the final application uses no console window, do not simply print important errors to stdout.

Create an application log file in:

```text
%LOCALAPPDATA%\GoogleClassHelp\logs\
```

The application should log:

- startup;
- backend startup;
- frontend serving;
- OAuth errors;
- Google Classroom API errors;
- unexpected exceptions;
- shutdown.

Do not log:

- OAuth access tokens;
- refresh tokens;
- client secrets unnecessarily;
- sensitive user data.

# Port handling

Prefer localhost only.

Bind the server to:

```text
127.0.0.1
```

Do not expose the local dashboard to the entire LAN unless explicitly required.

If port `8000` is already occupied:

- detect the problem;
- provide a useful error;
- optionally select another local port if the architecture supports it.

The browser URL must use the actual selected port.

# Security

The application is intended to run locally.

Follow these principles:

- Backend binds to localhost.
- OAuth tokens are stored per user.
- No tokens are sent to the frontend.
- No `credentials.json` is distributed as a visible plaintext standalone file.
- Do not hard-code user tokens.
- Do not expose credentials through API endpoints.
- Do not put secrets into frontend JavaScript.
- Do not store secrets in localStorage.
- Do not commit secrets to Git.
- Use `.gitignore` appropriately.
- Do not claim desktop OAuth client credentials are impossible to extract.

# Windows integration

After the basic application works, prepare the architecture for:

- Start Menu shortcut;
- Desktop shortcut;
- optional Windows startup;
- optional installer;
- application icon;
- clean uninstall;
- version information.

Do NOT implement Windows startup automatically unless explicitly requested. Make it optional.

# Application icon

Configure Nuitka/Windows so the executable can have a proper:

```text
GoogleClassHelp.ico
```

icon.

Do not use the default Python icon in the final release.

# No-console build

During development, keep console output available.

For the final release, use the appropriate Nuitka GUI/no-console configuration so that:

```text
GoogleClassHelp.exe
```

does not open a CMD window.

However, errors must still be available through the log file and/or a user-friendly error dialog.

# Dependency cleanup

Review:

```text
backend/requirements.txt
```

and remove dependencies that are only needed for development.

Do not remove anything required by the actual application.

The final Python runtime must contain everything required to run:

- FastAPI;
- Uvicorn;
- Google API client;
- Google OAuth;
- SQLite/database dependencies;
- all existing application functionality.

# Do not break existing Google Classroom functionality

The current application already has Google Classroom API integration.

Preserve:

- courses;
- coursework;
- student submissions;
- grades;
- due dates;
- existing API logic;
- current OAuth behavior.

Do not change scopes simply because packaging is being implemented.

The application currently uses read-only Classroom permissions where possible. Preserve that security model.

# Development mode

Keep development mode easy to use.

I should still be able to run:

```text
cd backend
uvicorn main:app --reload
```

and separately:

```text
cd frontend
npm run dev
```

during development.

Production packaging must be separate from development mode.

# Files to create/change

Determine the appropriate implementation, but likely create/update:

```text
backend/launcher.py
backend/path_config.py
backend/oauth.py              # only if useful
build.bat
.gitignore
README.md
```

and modify:

```text
backend/main.py
backend requirements/configuration
frontend configuration if required
```

Do not blindly create files that are unnecessary.

# README

Update `README.md` with two separate sections.

## DEVELOPMENT

Explain how to:

- activate `.venv`;
- install backend requirements;
- run FastAPI;
- run Vite frontend.

## PRODUCTION BUILD

Explain how to:

- build frontend;
- run the Nuitka build;
- find the resulting executable;
- test the release build;
- where user data/token/logs are stored.

# Acceptance criteria

The implementation is complete only when all of these are true:

- [ ] `npm run build` successfully creates `frontend/dist`.
- [ ] FastAPI can serve the production frontend.
- [ ] The frontend works without Vite dev server.
- [ ] `launcher.py` can start the production backend.
- [ ] The browser opens automatically after startup.
- [ ] No hard-coded project path exists.
- [ ] OAuth credentials are not distributed as a visible plaintext `credentials.json` file.
- [ ] OAuth tokens are stored per user under an appropriate user-data directory.
- [ ] Google OAuth still works.
- [ ] Google Classroom API still works.
- [ ] Existing dashboard functionality still works.
- [ ] Nuitka successfully produces the Windows executable.
- [ ] The executable works on a machine without the project source code.
- [ ] The executable works without PyCharm/VS Code.
- [ ] The executable works without the project's virtual environment.
- [ ] The executable does not require Node.js/npm at runtime.
- [ ] The final executable does not open a console window.
- [ ] Logs are written to the user's application-data directory.
- [ ] The application binds only to localhost.
- [ ] The application shuts down cleanly.
- [ ] Development mode still works separately.
- [ ] No credentials, OAuth tokens, or other secrets are committed to Git.

# Important implementation rule

Before changing code, inspect the existing project structure and existing backend/frontend implementation.

Do not rewrite working code unnecessarily.

First identify:

- how FastAPI is currently initialized;
- how Google OAuth is currently implemented;
- where credentials are loaded;
- where `token.json` is stored;
- how the frontend calls the backend;
- what frontend framework/router is used;
- where the SQLite database is stored;
- what API routes already exist.

Then implement the smallest robust set of changes required to achieve the production application described above.

After implementation, provide:

1. files changed;
2. exact commands for development;
3. exact commands for production build;
4. exact Nuitka command/options used;
5. final output location;
6. how OAuth behaves on first launch;
7. where token/database/log files are stored;
8. how to test the compiled `.exe`;
9. any limitations or security considerations.
