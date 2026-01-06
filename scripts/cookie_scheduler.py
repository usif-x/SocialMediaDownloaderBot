#!/usr/bin/env python3
"""
Cookie Scheduler - Runs cookie refresher at random intervals (1-5 minutes)
Uses APScheduler to trigger refreshes with randomized delays for anti-detection.
"""

import asyncio
import logging
import random
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from youtube_cookie_refresher import YouTubeCookieRefresher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("cookie_scheduler.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class CookieScheduler:
    """Schedules cookie refreshes at randomized intervals"""

    def __init__(
        self,
        cookies_file: str = "/app/cookies/cookies.txt",
        profile_dir: str = "/app/browser_profile",
        headless: bool = True,
        min_interval_minutes: int = 1,
        max_interval_minutes: int = 5,
    ):
        self.refresher = YouTubeCookieRefresher(
            cookies_file=cookies_file, profile_dir=profile_dir, headless=headless
        )

        self.min_interval_minutes = min_interval_minutes
        self.max_interval_minutes = max_interval_minutes

        self.scheduler = AsyncIOScheduler()
        self.is_running = False

    async def refresh_cookies_task(self):
        """
        Task that refreshes cookies and schedules the next run.
        This approach allows for truly random intervals between runs.
        """
        try:
            logger.info("=" * 60)
            logger.info(f"Cookie refresh triggered at {datetime.now()}")

            # Run the cookie refresh
            success = await self.refresher.fetch_cookies()

            if success:
                logger.info("✅ Cookie refresh completed successfully")
            else:
                logger.warning("⚠️  Cookie refresh failed, will retry next cycle")

        except Exception as e:
            logger.error(f"Error in refresh task: {e}", exc_info=True)

        finally:
            # Schedule next run with random delay
            self.schedule_next_run()

    def schedule_next_run(self):
        """Schedule the next cookie refresh at a random interval"""
        if not self.is_running:
            return

        # Generate random interval (in minutes)
        interval_minutes = random.uniform(
            self.min_interval_minutes, self.max_interval_minutes
        )

        # Convert to seconds for scheduler
        interval_seconds = interval_minutes * 60

        logger.info(
            f"📅 Next refresh scheduled in {interval_minutes:.2f} minutes "
            f"({interval_seconds:.1f} seconds)"
        )

        # Schedule the job (remove old job if exists)
        if self.scheduler.get_job("refresh_job"):
            self.scheduler.remove_job("refresh_job")

        # Add new job with calculated delay
        run_date = datetime.now().timestamp() + interval_seconds

        self.scheduler.add_job(
            self.refresh_cookies_task,
            trigger="date",
            run_date=datetime.fromtimestamp(run_date),
            id="refresh_job",
            replace_existing=True,
        )

    async def run_initial_refresh(self):
        """Run initial cookie refresh on startup"""
        logger.info("Running initial cookie refresh...")

        # Add small random delay before first run (5-15 seconds)
        initial_delay = random.uniform(5, 15)
        logger.info(f"Starting in {initial_delay:.1f} seconds...")
        await asyncio.sleep(initial_delay)

        await self.refresh_cookies_task()

    def start(self):
        """Start the scheduler"""
        logger.info("=" * 60)
        logger.info("YouTube Cookie Scheduler Starting")
        logger.info("=" * 60)
        logger.info(f"Cookies file: {self.refresher.cookies_file}")
        logger.info(f"Browser profile: {self.refresher.profile_dir}")
        logger.info(f"Headless mode: {self.refresher.headless}")
        logger.info(
            f"Random interval: {self.min_interval_minutes}-{self.max_interval_minutes} minutes"
        )
        logger.info("=" * 60)

        self.is_running = True
        self.scheduler.start()

        # Run initial refresh
        asyncio.create_task(self.run_initial_refresh())

        logger.info("✅ Scheduler started successfully")

    def stop(self):
        """Stop the scheduler gracefully"""
        logger.info("Stopping scheduler...")
        self.is_running = False
        self.scheduler.shutdown(wait=False)
        logger.info("✅ Scheduler stopped")


async def main():
    """Main function"""
    import argparse

    parser = argparse.ArgumentParser(
        description="YouTube Cookie Scheduler - Refreshes cookies at random intervals"
    )
    parser.add_argument(
        "--cookies-file",
        default="cookies.txt",
        help="Path to cookies file (default: cookies.txt)",
    )
    parser.add_argument(
        "--profile-dir",
        default="./browser_profile",
        help="Browser profile directory (default: ./browser_profile)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run browser in headless mode (default: True)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser with visible UI (for debugging)",
    )
    parser.add_argument(
        "--min-interval",
        type=int,
        default=1,
        help="Minimum interval in minutes (default: 1)",
    )
    parser.add_argument(
        "--max-interval",
        type=int,
        default=5,
        help="Maximum interval in minutes (default: 5)",
    )

    args = parser.parse_args()

    # Override headless if --no-headless is specified
    headless = not args.no_headless if args.no_headless else args.headless

    # Create scheduler
    scheduler = CookieScheduler(
        cookies_file=args.cookies_file,
        profile_dir=args.profile_dir,
        headless=headless,
        min_interval_minutes=args.min_interval,
        max_interval_minutes=args.max_interval,
    )

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        logger.info(f"\nReceived signal {sig}, shutting down...")
        scheduler.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start scheduler
    scheduler.start()

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
