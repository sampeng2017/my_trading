# Setting Up Automated Trading Schedules on Railway

Since Railway does not support running both a persistent Web Service (your dashboard) and a scheduled Cron Job in the same service instance, you need to set up a dedicated **Cron Service**.

## Step 1: Create a New Service
1.  Go to your project dashboard on [Railway.app](https://railway.app/).
2.  Click **+ New** -> **GitHub Repo**.
3.  Select the **same repository** (`my_trading`) again.
4.  This will spawn a second service card in your project.

## Step 2: Configure as Cron Job
1.  Click on the new service card.
2.  Go to **Settings** -> **Deploy**.
3.  **Critical**: Set the **Start Command** to:
    ```bash
    python src/main_orchestrator.py --mode auto
    ```
4.  Scroll down to **Cron Schedule** and click **Add Cron Schedule**.
5.  Enter the schedule: `*/30 13-22 * * 1-5`
    *   **Meaning**: Runs every 30 minutes.
    *   **Hours**: 13:00 UTC to 22:00 UTC (approx 6:00 AM - 3:00 PM PST).
    *   **Days**: Monday to Friday (1-5).
    *   *Note: Adjust UTC hours based on daylight savings if precision is critical, or just extend the range (e.g. 13-23).*

## Step 3: Environment Variables
1.  Go to the **Variables** tab of the new service.
2.  You can manually copy variables, **OR** verify if Railway allows sharing variables (Shared Variables feature).
3.  Ensure `DATABASE_URL` / `DB_MODE` / API Keys match your main service so they talk to the same database.

## How It Works
- Every 30 minutes, Railway boots this script.
- The script checks the time:
    - **6:00-6:30 AM**: Runs `premarket` logic.
    - **6:30-1:00 PM**: Runs `market` logic.
    - **1:00-2:00 PM**: Runs `postmarket` logic **(RUN ONCE)**.
- **Safety**: The script checks the database. If `postmarket` has already run successfully today, it skips execution to preventing sending double emails.
