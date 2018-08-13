import logging
import datetime
import pickle
import os.path
import os
import math
from time import time
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, JobQueue
from threading import Event

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
REQUEST_KWARGS = {}
if 'TELEGRAM_SOCKS5_PROXY_URL' in os.environ:
    REQUEST_KWARGS['proxy_url'] = os.environ['TELEGRAM_SOCKS5_PROXY_URL']

    if 'TELEGRAM_SOCKS5_PROXY_LOGIN' in os.environ and 'TELEGRAM_SOCKS5_PROXY_PASSWORD' in os.environ:
        REQUEST_KWARGS['urllib3_proxy_kwargs'] = {
            'username': os.environ['TELEGRAM_SOCKS5_PROXY_LOGIN'],
            'password': os.environ['TELEGRAM_SOCKS5_PROXY_PASSWORD']
        }

updater = Updater(token=os.environ['INTERSTELLAR_BOT_TOKEN'],
                  request_kwargs=REQUEST_KWARGS)

job_queue = updater.job_queue
dispatcher = updater.dispatcher

FILENAME = 'date.dat'
QUEUE_FILENAME = 'queue.dat'
DAILY_TIME = datetime.time(10)


def write_to_file(chat_id):
    now = datetime.datetime.now()
    now_midnight = datetime.datetime(now.year, now.month, now.day)
    data = read_from_file()
    data[chat_id] = now_midnight
    pickle.dump(data, open(FILENAME, 'wb+'))


def read_from_file():
    if not os.path.exists(FILENAME):
        return {}
    return pickle.load(open(FILENAME, 'rb+'))


def dump_jobs(job_queue):
    job_tuples = job_queue._queue.queue

    with open(QUEUE_FILENAME, 'wb+') as fp:
        for next_t, job in job_tuples:
            # Back up objects
            _job_queue = job._job_queue
            _remove = job._remove
            _enabled = job._enabled

            # Replace un-pickleable threading primitives
            job._job_queue = None  # Will be reset in jq.put
            job._remove = job.removed  # Convert to boolean
            job._enabled = job.enabled  # Convert to boolean

            # Pickle the job
            pickle.dump((next_t, job), fp)

            # Restore objects
            job._job_queue = _job_queue
            job._remove = _remove
            job._enabled = _enabled


def restore_jobs(job_queue):
    now = time()
    with open(QUEUE_FILENAME, 'rb+') as fp:
        while True:
            try:
                next_t, job = pickle.load(fp)
            except EOFError:
                break

            enabled = job._enabled
            removed = job._remove

            job._enabled = Event()
            job._remove = Event()

            if enabled:
                job._enabled.set()

            if removed:
                job._remove.set()

            next_t -= now  # Convert from absolute to relative time

            job_queue._put(job, next_t)


def jobs(bot, update):
    jobs = job_queue.jobs()
    response = "["
    for job in jobs:
        response += str(job.context) + ", "
    response += "]"
    bot.send_message(chat_id=update.message.chat_id, text=response)


def when(bot, update):
    showAlert(bot, update.message.chat_id)


def getDaysSinceLastAccident(chat_id):
    now = datetime.datetime.now()
    data = read_from_file()
    if chat_id in data:
        last_accident = data[chat_id]
    else:
        last_accident = now
    diff = now - last_accident
    days = math.floor(diff.days)
    return days


def showAlert(bot, chat_id):
    days = getDaysSinceLastAccident(chat_id)

    bot.send_message(chat_id=chat_id,
                     text=f'Days since last Interstellar accident: {days}')


def echo(bot, update):
    msg = update.message if not update.message is None else update.edited_message
    if('интерстеллар' in msg.text.lower()
            .replace("a", "а")
            .replace("e", "е")
            .replace("c", "с")
            .replace("p", "р")):
        days = getDaysSinceLastAccident(msg.chat_id)
        write_to_file(msg.chat_id)
        if days > 0:
            showAlert(bot, msg.chat_id)


def alert(bot, job):
    showAlert(bot, job.context)


def start(bot, update):
    jobs = job_queue.jobs()
    for job in job_queue.jobs():
        if job.context == update.message.chat_id:
            return
    job_queue.run_daily(alert, DAILY_TIME,
                        context=update.message.chat_id)
    dump_jobs(job_queue)


def main():
    if not os.path.exists(QUEUE_FILENAME):
        dump_jobs(job_queue)
    else:
        restore_jobs(job_queue)

    when_handler = CommandHandler('when', when)
    start_handler = CommandHandler('start', start)
    jobs_handler = CommandHandler('jobs', jobs)
    echo_handler = MessageHandler(
        Filters.text, echo, edited_updates=True)
    dispatcher.add_handler(echo_handler)
    dispatcher.add_handler(when_handler)
    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(jobs_handler)

    updater.start_polling()
    updater.idle()


if __name__ == '__main__':
    main()
