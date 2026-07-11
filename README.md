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

## ☁️ Deployment Instructions

The application can be seamlessly deployed on platforms like **Render** or **Vercel**. Since SQLite is used by default, please note that any local database file (`.db`) created inside ephemeral container storage will be reset on redeployment or restart. To ensure data persistence and reliable execution, we recommend the configurations detailed below.

---

### 🚀 Deploying on Vercel (Recommended with External Database)

Vercel provides a serverless platform. Because serverless functions have a read-only filesystem (except for `/tmp` which is ephemeral) and execute on-demand, running a local SQLite file directly on Vercel is not recommended for production data.

For Vercel deployments, we recommend configuring a persistent external database (such as PostgreSQL or Supabase) using the `DATABASE_URL` environment variable.

#### Step-by-Step Instructions

1. **Prerequisites & Setup:**
   - Make sure you have a Vercel account.
   - An external database URL is recommended for production (e.g., `postgresql://...` or a hosted SQLite service). If none is provided, the app will fallback to creating an ephemeral local SQLite file under `/tmp` during function invocation, which resets frequently.

2. **Deploy via Vercel CLI or Dashboard:**
   - **Vercel Dashboard:**
     - Go to [Vercel](https://vercel.com/) and click **Add New** > **Project**.
     - Connect your GitHub repository.
     - Select **Python** as the Framework Preset (Vercel automatically detects the project setup using `vercel.json` and `requirements.txt`).
   - **Vercel CLI:**
     - Install Vercel CLI (`npm i -g vercel`) and run:
       ```bash
       vercel
       ```

3. **Configure Environment Variables in Vercel:**
   - In your project settings, navigate to the **Environment Variables** tab and add:
     - `SECRET_KEY`: A secure random string for signing session cookies.
     - `DATABASE_URL`: Set this to your external PostgreSQL or MySQL connection string (e.g., `postgresql://user:pass@host:5432/dbname`).
       *Note: If you must use SQLite on Vercel for lightweight testing, set `DATABASE_URL` to `sqlite:////tmp/smashorpass.db` to use Vercel's writeable `/tmp` directory.*

4. **Background Tasks on Serverless:**
   - Since serverless functions spin down after serving requests, background threads and long-running schedulers (like our PyPI RSS feed polling) do not run continuously on Vercel.
   - To keep package queues fresh, you can set up a **Vercel Cron Job** or external uptime monitor to periodically call a webhook/route to trigger updates.

---

### 🌐 Deploying on Render

Render is a classic cloud platform that supports persistent disks and continuous background processes.

#### Step-by-Step Instructions

1. **Create a Render Account:**
   - Sign up or log in at [Render.com](https://render.com/).

2. **Create a New Web Service:**
   - Click **New +** and select **Web Service**.
   - Connect your GitHub repository.

3. **Configure the Service Settings:**
   - **Name:** Choose a unique name (e.g., `smash-or-pass-pypi`).
   - **Environment:** Select `Python 3` (or `Python`).
   - **Branch:** Select your target deployment branch.
   - **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command:**
     ```bash
     gunicorn app:app --bind 0.0.0.0:$PORT
     ```

4. **Add Environment Variables:**
   - Click on the **Environment** tab on Render and add:
     - `SECRET_KEY`: A secure random string.
     - `DATABASE_URL`: Set to `sqlite:////var/data/smashorpass.db?timeout=30` to utilize Render's Persistent Disk.

5. **Configure Persistent Disk:**
   - Go to the **Disks** tab in your Web Service dashboard on Render.
   - Click **Add Disk**:
     - **Name:** `smashorpass-db`
     - **Mount Path:** `/var/data`
     - **Size:** `1 GB` (More than enough for thousands of packages).

6. **Deploy!**
   - Click **Deploy Web Service**. Render will build the container, start Gunicorn, initialize the database automatically on startup, and launch the site at a public URL (e.g., `https://smash-or-pass-pypi.onrender.com`).
