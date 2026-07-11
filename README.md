# SmashOrPass PyPI 🐍🔥

A modern, highly-polished web application that lets you "Smash" or "Pass" Python packages! Sign up, vote on package cards Tinder-style, view voting histories, check out leaderboards based on community ratings, and view full details and metrics (total downloads, GitHub stars, licenses, etc.) for each package.

---

## 🚀 Key Features

1. **Modern Responsive UI:**
   - Designed with custom dark-themed elements, gradients, animations, and icons (via Tailwind CSS and FontAwesome).
   - Card swiping / Tinder-style card container with clean, responsive interaction.
2. **On-Demand Package Ingestion:**
   - Ingests Python package names from PyPI's `/simple/` Index in bulk into a local queue (`PypiQueue`) in seconds.
   - Fetches metadata, downloads, and GitHub stars **dynamically on-demand** when requested for voting, avoiding rate-limiting or heavy resource usage.
3. **Advanced Quality Filtering:**
   - Weeds out low-quality/boilerplate packages (empty descriptions, placeholders like "work in progress", "test package", "todo", etc.) to guarantee a high-quality voting catalog.
4. **User Accounts & Session Tracking:**
   - User authentication (secure registration, login, and logout) powered by `Flask-Login` and hashed passwords using `Werkzeug`.
   - Guest session voting allows immediate play without logging in.
5. **Detailed Stats & Rating Scales:**
   - Packages are graded on a community-driven scale of `0.0` to `10.0` calculated by `(Smashes / Total Votes) * 10`.
   - Beautiful voting breakdown progress bars display percentages of s_smashes and passes.
   - Detailed page for each package showing its version, license, monthly downloads, GitHub stars, and README/description.
6. **Automatic Freshness & RSS Updates:**
   - Background thread listens to PyPI's `updates.xml` RSS feed, automatically updating versions and metadata or adding newly updated high-quality packages.

---

## 📦 Dependencies

The application relies on the following key dependencies:
- **Flask**: The micro web framework.
- **Flask-SQLAlchemy**: ORM wrapper for database storage.
- **Flask-Login**: Session and authentication manager.
- **httpx**: Asynchronous-capable HTTP requests (used for API integrations).
- **xmltodict**: For parsing PyPI RSS updates.
- **gunicorn**: WSGI HTTP server for production deployment on Render.
- **pytest**: For testing.

---

## 💻 Local Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Application
```bash
python app.py
```
The application will automatically:
1. Initialize the SQLite database.
2. Populate the package ingestion queue.
3. Start the background RSS polling scheduler.
4. Serve the web application at `http://localhost:5000`.

### 3. Run Tests
```bash
pytest
```

---

## ☁️ How to Deploy on Render

Deploying this app on **Render** is straightforward. Since SQLite is server-less, Render's default ephemeral disk is suitable, but for persistence across redeployments, utilizing Render's **Persistent Disk** mount is recommended.

### Step-by-Step Instructions

1. **Create a Render Account:**
   - Sign up or log in at [Render.com](https://render.com/).

2. **Create a New Web Service:**
   - Click **New +** and select **Web Service**.
   - Connect your GitHub repository containing this project.

3. **Configure the Service Settings:**
   - **Name:** Choose a unique name (e.g., `smash-or-pass-pypi`).
   - **Environment:** Select `Python 3` (or `Python`).
   - **Branch:** Select the branch you want to deploy from (e.g., `main` or `feat/pypi-smash-or-pass`).
   - **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command:**
     ```bash
     gunicorn app:app --bind 0.0.0.0:$PORT
     ```

4. **Add Environment Variables (Optional):**
   - Click on the **Environment** tab on Render and add:
     - `SECRET_KEY`: A random, secure string for Flask session signing.
     - `DATABASE_URL`: By default, the app uses local SQLite (`sqlite:///smashorpass.db`). If you use SQLite with a persistent disk, set it to `sqlite:////var/data/smashorpass.db` (see Step 5).

5. **Configure Persistent Disk (Recommended for SQLite):**
   - SQLite files stored in the container will be reset on every deploy or restart unless a persistent disk is used.
   - Go to the **Disks** tab in your Web Service dashboard on Render.
   - Click **Add Disk**:
     - **Name:** `smashorpass-db`
     - **Mount Path:** `/var/data`
     - **Size:** `1 GB` (More than enough for thousands of packages).
   - In the **Environment** variables tab, update your database URL:
     - **Key:** `DATABASE_URL`
     - **Value:** `sqlite:////var/data/smashorpass.db?timeout=30`

6. **Deploy!**
   - Click **Deploy Web Service**. Render will build the container, install packages from `requirements.txt`, start Gunicorn, and launch your application.
   - Once complete, you will receive a public URL (e.g., `https://smash-or-pass-pypi.onrender.com`) to access your PyPI Smash or Pass application!
