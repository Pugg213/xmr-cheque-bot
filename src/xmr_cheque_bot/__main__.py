"""Application entry point with APP_MODE support."""

import asyncio
import sys
from contextlib import asynccontextmanager

from xmr_cheque_bot.config import get_settings
from xmr_cheque_bot.logging import configure_logging, get_logger
from xmr_cheque_bot.monero_rpc import MoneroWalletRPC
from xmr_cheque_bot.payment_monitor import PaymentMonitor
from xmr_cheque_bot.storage import RedisStorage

# Import bot-related modules only when needed
try:
    from aiogram import Bot, Dispatcher
    from xmr_cheque_bot.bot import router
except ImportError:
    Bot = Dispatcher = router = None  # type: ignore


@asynccontextmanager
async def setup_storage():
    """Setup and teardown Redis storage."""
    storage = RedisStorage()
    try:
        yield storage
    finally:
        await storage.close()


@asynccontextmanager
async def setup_rpc():
    """Setup and teardown Monero RPC client."""
    settings = get_settings()
    rpc = MoneroWalletRPC(url=settings.monero_rpc_url)
    try:
        yield rpc
    finally:
        await rpc.close()


async def run_bot() -> None:
    """Run Telegram bot (aiogram polling)."""
    if Bot is None or Dispatcher is None:
        raise RuntimeError("aiogram not installed, cannot run bot mode")
    
    settings = get_settings()
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    
    # Include router
    dp.include_router(router)
    
    logger = get_logger()
    logger.info("bot_starting", mode="polling")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


async def run_monitor() -> None:
    """Run payment monitor (background worker)."""
    logger = get_logger()
    logger.info("monitor_starting")
    
    async with setup_storage() as storage:
        async with setup_rpc() as rpc:
            monitor = PaymentMonitor(storage=storage, rpc=rpc)
            await monitor.run_forever()


async def run_both() -> None:
    """Run both bot and monitor concurrently."""
    logger = get_logger()
    logger.info("both_modes_starting")
    
    # Create tasks for concurrent execution
    bot_task = asyncio.create_task(run_bot(), name="bot")
    monitor_task = asyncio.create_task(run_monitor(), name="monitor")
    
    # Wait for either task to complete or cancellation
    done, pending = await asyncio.wait(
        [bot_task, monitor_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    
    # Cancel remaining tasks
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    # Check for exceptions in completed tasks
    for task in done:
        exc = task.exception()
        if exc is not None:
            raise exc


async def main() -> None:
    """Main entry point."""
    configure_logging()
    logger = get_logger()
    
    settings = get_settings()
    app_mode = settings.app_mode.lower()
    
    logger.info("xmr_cheque_bot.starting", version="0.1.0", mode=app_mode)
    
    try:
        if app_mode == "bot":
            await run_bot()
        elif app_mode == "monitor":
            await run_monitor()
        elif app_mode == "both":
            await run_both()
        else:
            logger.error("invalid_app_mode", mode=app_mode)
            print(f"Error: Invalid APP_MODE='{app_mode}'. Use: bot|monitor|both", file=sys.stderr)
            sys.exit(1)
    except asyncio.CancelledError:
        logger.info("shutdown_requested", reason="cancelled")
        raise
    except KeyboardInterrupt:
        logger.info("shutdown_requested", reason="keyboard_interrupt")
        raise
    except Exception as e:
        logger.error("fatal_error", error=str(e))
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except asyncio.CancelledError:
        print("\nCancelled...")
        sys.exit(0)
