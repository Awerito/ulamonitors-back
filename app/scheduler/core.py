from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.scheduler.jobs.simulator import simulate_readings
from app.utils.logger import logger

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    """Register the jobs and start the scheduler."""
    # Every 5 minutes: fast enough that charts visibly move during a class,
    # slow enough that a day of history stays a manageable number of documents.
    scheduler.add_job(simulate_readings, CronTrigger(minute="*/5"))
    scheduler.start()
    logger.info("[scheduler] started")


def stop_scheduler() -> None:
    """Stop the scheduler on shutdown."""
    scheduler.shutdown(wait=False)
    logger.info("[scheduler] stopped")
