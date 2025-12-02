import schedule
import time
from scripts.run_bot import run_cycle

schedule.every(1).minutes.do(run_cycle)

while True:
    schedule.run_pending()
    time.sleep(1)